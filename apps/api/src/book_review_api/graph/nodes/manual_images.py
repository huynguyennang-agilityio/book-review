"""Node `manual_images` (chế độ chọn ảnh manual): không gọi Fal.

Dựng prompt cho mọi ảnh (mỗi nhân vật 1 sheet, mỗi ảnh cảnh 1 prompt theo `image_plan`), dừng ở
interrupt `upload_images` chờ người dùng tải đủ ảnh, rồi ghi vào đúng chỗ pipeline cũ:
`characters_approved`, `scene.images`, `asset_refs`. Ảnh cảnh qua `fit_9_16`; tiền ảnh = 0.

Resume: `{"uploads": {"character:<slug>": path, "<scene_id>:<ref>": path}}` hoặc `{"cancel": true}`.
Thiếu ảnh hoặc đường dẫn không thuộc project thì hỏi lại (payload kèm `errors`), không fail run.
Nhân vật đã duyệt của cùng series trong Store được dùng lại, không cần ảnh mới.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any

from langgraph.config import get_config

from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.characters import (
    _approved_from_store,
    sheet_prompt,
    slugify,
)
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.nodes.review import _save_approved, _wait_for_user
from book_review_api.graph.nodes.scene_images import compose_prompt, fit_9_16
from book_review_api.graph.state import BookReviewState
from book_review_api.storyboard.images import PromptWriter, default_prompts, image_plan
from book_review_api.storyboard.schema import SceneImage, Storyboard
from book_review_api.uploads import UPLOAD_NAME, is_upload_path

log = logging.getLogger(__name__)

MAX_ROUNDS = 20  # chặn vòng hỏi lại vô hạn khi client gửi sai mãi


def _project_id() -> str | None:
    try:
        value = get_config().get("configurable", {}).get("project_id")
    except RuntimeError:
        return None
    return str(value) if value else None


def _valid_path(project_id: str | None, path: Any) -> bool:
    if not isinstance(path, str):
        return False
    parts = path.split("/")
    if project_id is not None:
        from uuid import UUID

        try:
            return is_upload_path(UUID(project_id), path)
        except ValueError:
            return False
    return len(parts) == 3 and parts[0] == "uploads" and UPLOAD_NAME.fullmatch(parts[2]) is not None


def make_manual_images_node(
    settings: Settings | None = None,
    prompt_writer: PromptWriter | None = None,
    approved_lookup: Any = _approved_from_store,
) -> NodeFn:
    @node
    def manual_images(state: BookReviewState) -> NodeUpdate:
        cfg = settings or get_settings()
        raw = state.get("storyboard")
        if not raw:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        sb = Storyboard.model_validate(raw)
        media_dir = Path(cfg.media_dir)
        series = state["book"].get("series") if "book" in state else None
        plan = image_plan(sb, cfg)
        prompts = (prompt_writer or default_prompts)(sb, plan)
        by_name = {c.name: c for c in sb.characters}

        reused: dict[str, dict[str, Any]] = {}
        char_items: list[dict[str, Any]] = []
        for ch in sb.characters[: cfg.character_max]:
            slug = slugify(ch.name)
            approved = approved_lookup(series, slug)
            if approved:
                reused[slug] = {"name": ch.name, "sheet_path": str(approved["sheet_path"])}
                continue
            char_items.append(
                {
                    "key": f"character:{slug}",
                    "slug": slug,
                    "name": ch.name,
                    "prompt": sheet_prompt(ch, sb.style_prompt_en, 1),
                }
            )
        scene_items: list[dict[str, Any]] = []
        for scene in sb.scenes:
            for k in range(plan[scene.id]):
                p = prompts[scene.id][k]
                # Không có sheet tham chiếu nên nhúng mô tả ngoại hình vào prompt.
                looks = "; ".join(
                    f"{n}: {by_name[n].description_en.strip().rstrip('.')}"
                    for n in p.characters
                    if n in by_name
                )
                body = (
                    f"{p.prompt_en.strip().rstrip('.')}. Characters: {looks}"
                    if looks
                    else (p.prompt_en)
                )
                scene_items.append(
                    {
                        "key": f"{scene.id}:{k}",
                        "scene_id": scene.id,
                        "ref": k,
                        "narration": scene.narration_vi,
                        "prompt": compose_prompt(sb.style_prompt_en, body, []),
                        "characters": p.characters,
                    }
                )
        required = [i["key"] for i in char_items + scene_items]
        project_id = _project_id()

        errors: list[dict[str, str]] = []
        uploads: dict[str, str] = {}
        for _ in range(MAX_ROUNDS):
            update, decision = _wait_for_user(
                {
                    "type": "upload_images",
                    "message": "Tải một ảnh cho mỗi prompt.",
                    "characters": char_items,
                    "scenes": scene_items,
                    "reused_characters": reused,
                    "required": required,
                    "errors": errors,
                    "cost": state.get("cost") or {},
                }
            )
            if update:
                return update
            raw_up = decision.get("uploads")
            got = raw_up if isinstance(raw_up, dict) else {}
            errors = []
            for key in required:
                path = got.get(key)
                if path is None:
                    errors.append({"key": key, "code": "MISSING"})
                elif not _valid_path(project_id, path) or not (media_dir / path).is_file():
                    errors.append({"key": key, "code": ErrorCode.VALIDATION_ERROR.value})
            if not errors:
                uploads = {k: str(got[k]) for k in required}
                break
        else:
            return {"status": "failed", "error_code": ErrorCode.VALIDATION_ERROR.value}

        approved_new = {
            i["slug"]: {"name": i["name"], "sheet_path": uploads[i["key"]]} for i in char_items
        }
        approved = {**reused, **approved_new}
        asset_refs = {f"character:{s}:approved": v["sheet_path"] for s, v in approved.items()}
        out_dir = media_dir / "images" / "scenes"
        out_dir.mkdir(parents=True, exist_ok=True)
        slot_paths: dict[tuple[int, int], str] = {}
        for item in scene_items:
            try:
                payload = fit_9_16(
                    (media_dir / uploads[item["key"]]).read_bytes(),
                    cfg.scene_out_width,
                    cfg.scene_out_height,
                )
            except OSError:
                return {"status": "failed", "error_code": ErrorCode.INVALID_IMAGE.value}
            name = hashlib.sha1(payload).hexdigest()[:20] + ".jpg"
            (out_dir / name).write_bytes(payload)
            rel = (out_dir / name).relative_to(media_dir).as_posix()
            slot_paths[(item["scene_id"], item["ref"])] = rel
            asset_refs[f"image:{item['scene_id']}:{item['ref']}"] = rel
        prompt_of = {(i["scene_id"], i["ref"]): i["prompt"] for i in scene_items}
        for scene in sb.scenes:
            scene.images = [
                SceneImage(prompt_en=prompt_of[(scene.id, k)], path=slot_paths[(scene.id, k)])
                for k in range(plan[scene.id])
            ]
        _save_approved(series, approved_new)
        prompt_of_char = {i["slug"]: i["prompt"] for i in char_items}
        return {
            "storyboard": sb.model_dump(mode="json"),
            "character_candidates": {
                s: {
                    "name": v["name"],
                    "images": [v["sheet_path"]],
                    "manual": True,
                    "prompt": prompt_of_char.get(s, ""),
                }
                for s, v in approved.items()
            },
            "characters_approved": approved,
            "asset_refs": asset_refs,
            "cost": {"usd": 0.0, "images": 0.0},
            "feedback": [{"type": "manual_images", "images": len(required)}],
        }

    return manual_images
