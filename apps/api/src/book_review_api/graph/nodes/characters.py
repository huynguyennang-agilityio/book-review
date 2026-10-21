"""Node `character_sheets` (ngày 16): 4 ứng viên sheet nhiều góc cho mỗi nhân vật chính.

Nhân vật đã duyệt của cùng series nằm trong Store (`("characters", <series>)`, ghi ở ngày 17/20)
thì dùng lại, không tạo mới. Chi phí cộng vào `state.cost`; vượt `options.budget_usd` thì dừng
với `BUDGET_EXCEEDED`. Ảnh ghi vào `<media_dir>/characters/<job_key>/`, file đã có thì dùng lại.
"""

import hashlib
import logging
import re
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from langgraph.config import get_config, get_store

from book_review_api.cancel import CancelFlags
from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import Cancelled, NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.providers.image_fal import ImageError, ImageProvider
from book_review_api.storyboard.schema import Character, Storyboard

log = logging.getLogger(__name__)

SHEET_PROMPT = (
    "Character reference sheet of {description}. Several views of the same person on one plain "
    "neutral light-gray background: front view, three-quarter view, side profile and a full-body "
    "standing pose, identical face, hairstyle, outfit and proportions in every view, evenly "
    "spaced, clean even lighting. {style}. Candidate variation {n}. "
    "no text, no letters, no captions, no labels, no watermark, no logo."
)
SAFE_DESCRIPTION = "a friendly adult person in everyday clothes"


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "nhan-vat"


def base_seed(name: str) -> int:
    """Seed cố định theo tên nhân vật; ứng viên thứ i dùng `base + i`."""
    return int(hashlib.sha1(name.encode()).hexdigest()[:7], 16)


def sheet_prompt(character: Character, style: str, n: int, safe: bool = False) -> str:
    description = SAFE_DESCRIPTION if safe else character.description_en.strip().rstrip(".")
    return SHEET_PROMPT.format(description=description, style=style.strip().rstrip("."), n=n)


def job_key(storyboard: Storyboard, cfg: Settings) -> str:
    parts = [storyboard.style_prompt_en, str(cfg.character_sheet_images)]
    parts += [f"{c.name}|{c.description_en}" for c in storyboard.characters[: cfg.character_max]]
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:16]


def _thread_id() -> str | None:
    try:
        thread_id = get_config().get("configurable", {}).get("thread_id")
    except RuntimeError:
        return None
    return str(thread_id) if thread_id else None


def _approved_from_store(series: str | None, slug: str) -> dict[str, Any] | None:
    """Nhân vật đã duyệt của series (nếu có Store và có bản ghi)."""
    if not series:
        return None
    try:
        store = get_store()
    except RuntimeError:  # chạy không có Store (test khung, script)
        return None
    try:
        item = store.get(("characters", slugify(series)), slug)
    except Exception:  # noqa: BLE001
        log.warning("không đọc được Store nhân vật", exc_info=True)
        return None
    value = item.value if item else None
    return value if isinstance(value, dict) and value.get("sheet_path") else None


def make_character_sheets_node(
    provider: ImageProvider,
    settings: Settings | None = None,
    cancel_flags: CancelFlags | None = None,
    approved_lookup: Callable[[str | None, str], dict[str, Any] | None] = _approved_from_store,
) -> NodeFn:
    @node
    def character_sheets(state: BookReviewState) -> NodeUpdate:
        cfg = settings or get_settings()
        storyboard_raw = state.get("storyboard")
        if not storyboard_raw:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        sb = Storyboard.model_validate(storyboard_raw)
        characters = sb.characters[: cfg.character_max]
        if not characters:
            return {"character_candidates": {}}

        media_dir = Path(cfg.media_dir)
        out_dir = media_dir / "characters" / job_key(sb, cfg)
        series = state["book"].get("series") if "book" in state else None
        budget = (state.get("options") or {}).get("budget_usd")
        spent = (state.get("cost") or {}).get("usd", 0.0)
        thread_id = _thread_id()

        def cancelled() -> bool:
            return bool(cancel_flags and thread_id and cancel_flags.is_set(thread_id))

        candidates: dict[str, Any] = {}
        asset_refs: dict[str, str] = {}
        job_ids: dict[str, str] = {}
        new_images = 0

        todo: list[tuple[Character, str, int]] = []
        for ch in characters:
            slug = slugify(ch.name)
            approved = approved_lookup(series, slug)
            if approved:
                path = str(approved["sheet_path"])
                candidates[slug] = {"name": ch.name, "images": [path], "reused": True}
                asset_refs[f"character:{slug}:approved"] = path
                continue
            candidates[slug] = {"name": ch.name, "images": [None] * cfg.character_sheet_images}
            todo += [(ch, slug, i) for i in range(cfg.character_sheet_images)]

        # Chỉ tạo số ảnh mới mà ngân sách còn cho phép; file đã có trên đĩa không tốn tiền.
        pending = [t for t in todo if not (out_dir / f"{t[1]}_{t[2]}.jpg").exists()]
        over_budget = False
        if budget is not None:
            affordable = max(int((budget - spent + 1e-9) // cfg.price_image_usd), 0)
            if affordable < len(pending):
                over_budget = True
                allowed = {(t[1], t[2]) for t in pending[:affordable]}
                todo = [t for t in todo if (t[1], t[2]) in allowed or t not in pending]

        def make(item: tuple[Character, str, int]) -> tuple[str, int, str | None, str, bool]:
            ch, slug, i = item
            path = out_dir / f"{slug}_{i}.jpg"
            if path.exists():
                return slug, i, path.relative_to(media_dir).as_posix(), "", False
            job: list[str] = []
            for safe in (False, True):  # lần 2 dùng mô tả trung tính nếu bị bộ lọc chặn
                try:
                    img = provider.generate(
                        sheet_prompt(ch, sb.style_prompt_en, i + 1, safe),
                        seed=base_seed(ch.name) + i,
                        width=cfg.character_sheet_width,
                        height=cfg.character_sheet_height,
                        on_submit=job.append,
                        cancelled=cancelled,
                    )
                except ImageError:
                    log.warning("ảnh nhân vật %s #%d lỗi (safe=%s)", ch.name, i, safe)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(img.data)
                return slug, i, path.relative_to(media_dir).as_posix(), img.job_id, True
            return slug, i, None, job[-1] if job else "", False

        cancel_hit = False
        with ThreadPoolExecutor(max_workers=cfg.fal_concurrency) as pool:
            futures = [pool.submit(make, t) for t in todo]
            for fut in futures:
                try:
                    slug, i, rel, jid, billed = fut.result()
                except Cancelled:
                    cancel_hit = True
                    continue
                if rel:
                    candidates[slug]["images"][i] = rel
                    asset_refs[f"character:{slug}:{i}"] = rel
                if jid:
                    job_ids[f"character:{slug}:{i}"] = jid
                new_images += int(billed)

        for entry in candidates.values():
            entry["images"] = [p for p in entry["images"] if p]
        cost = {"usd": new_images * cfg.price_image_usd, "images": float(new_images)}
        update: NodeUpdate = {
            "character_candidates": candidates,
            "asset_refs": asset_refs,
            "fal_job_ids": job_ids,
            "cost": cost,
        }
        if cancel_hit:
            return {**update, "status": "cancelled", "error_code": ErrorCode.CANCELLED.value}
        if over_budget:
            return {**update, "status": "failed", "error_code": ErrorCode.BUDGET_EXCEEDED.value}
        if any(not e["images"] for e in candidates.values()):
            return {
                **update,
                "status": "failed",
                "error_code": ErrorCode.PROVIDER_UNAVAILABLE.value,
            }
        return update

    return character_sheets
