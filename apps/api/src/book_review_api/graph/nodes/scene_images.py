"""Node `scene_images` (ngày 18): ảnh cảnh thật bằng Fal, thay ảnh placeholder.

- Số ảnh mỗi cảnh theo `storyboard.images.image_plan` (25-35 ảnh/video, mỗi ảnh dùng cho ~2 shot
  qua `Shot.image_ref`).
- Tạo ở ~9:16 (bội số 16) rồi crop giữa và resize đúng 720×1280.
- Cảnh có nhân vật: tối đa 2 nhân vật, truyền sheet đã duyệt làm ảnh tham chiếu (Seedream edit).
- Bị bộ lọc chặn thì đổi sang cảnh ẩn dụ (`metaphor_en`, không người, không tham chiếu) và tạo lại.
  Vẫn hỏng thì dùng lại ảnh gần nhất đã có, để video không bị kẹt.
- Tài khoản Fal bị từ chối (hết tiền, 429...) thì dừng hẳn với `PROVIDER_QUOTA`: không đánh dấu
  `.blocked`, không mượn ảnh, không gửi thêm ảnh nào; nạp tiền xong chạy lại tạo nốt ảnh còn thiếu.
- Seedream đôi khi vẽ cả cảnh nằm ngang 90° (~24% ảnh text-to-image, đo 24/10). Có
  `orientation_check` thì mỗi ảnh mới được kiểm tra; xoay thì tạo lại một lần với seed khác (nếu
  còn ngân sách), vẫn xoay thì dùng cảnh ẩn dụ. Ảnh xoay không được ghi vào cache.
- Cache theo hash(prompt + seed + tham chiếu + kích thước): chạy lại không tạo và không tính tiền
  ảnh đã có. Prompt (model viết, mỗi lần một khác) cũng lưu ở `images/prompts/` theo storyboard,
  để chạy lại dùng đúng prompt cũ.
"""

import hashlib
import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PIL import Image

from book_review_api.cancel import CancelFlags
from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.characters import AccountStop, _thread_id, base_seed, slugify
from book_review_api.graph.nodes.common import Cancelled, NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.providers.image_fal import ImageAccountError, ImageError, ImageProvider
from book_review_api.storyboard.images import (
    ImagePrompt,
    PromptWriter,
    cached_prompts,
    default_prompts,
    image_plan,
)
from book_review_api.storyboard.orientation import OrientationCheck
from book_review_api.storyboard.schema import SceneImage, Storyboard

log = logging.getLogger(__name__)

NO_TEXT = "no text, no letters, no captions, no watermark, no logo."
JPEG_QUALITY = 92


def fit_9_16(data: bytes, width: int, height: int) -> bytes:
    """Crop giữa về đúng tỷ lệ width:height rồi resize thành đúng width×height (JPEG)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    target = width / height
    w, h = img.size
    if w / h > target:  # quá rộng: cắt hai bên
        new_w = round(h * target)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif w / h < target:  # quá cao: cắt trên dưới
        new_h = round(w / target)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def compose_prompt(style: str, body: str, names: list[str]) -> str:
    """Prompt cuối: câu dẫn ảnh tham chiếu (nếu có), nội dung cảnh, phong cách, khung dọc."""
    lead = ""
    if names:
        refs = "; ".join(f"image {i + 1} is {n}" for i, n in enumerate(names))
        lead = (
            f"Reference character sheets: {refs}. Keep each character's face, hairstyle, outfit "
            "and proportions identical to their sheet, but draw only the scene below, never the "
            "sheet layout or its gray background. "
        )
    scene = body.strip().rstrip(".")
    return f"{lead}{scene}. {style.strip().rstrip('.')}. Vertical 9:16 composition. {NO_TEXT}"


@dataclass(frozen=True)
class Job:
    scene_id: int
    ref: int
    prompt: ImagePrompt


@dataclass
class Result:
    rel: str | None
    prompt_en: str
    job_ids: list[str]
    billed: int
    rotated: int = 0


def cache_key(prompt: str, seed: int, refs: list[str], cfg: Settings) -> str:
    parts = [prompt, str(seed), *refs, f"{cfg.scene_image_width}x{cfg.scene_image_height}"]
    parts.append(f"{cfg.scene_out_width}x{cfg.scene_out_height}")
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:20]


def make_scene_images_node(
    provider: ImageProvider,
    settings: Settings | None = None,
    cancel_flags: CancelFlags | None = None,
    prompt_writer: PromptWriter | None = None,
    orientation_check: OrientationCheck | None = None,
) -> NodeFn:
    @node
    def scene_images(state: BookReviewState) -> NodeUpdate:
        cfg = settings or get_settings()
        raw = state.get("storyboard")
        if not raw:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        sb = Storyboard.model_validate(raw)
        media_dir = Path(cfg.media_dir)
        out_dir = media_dir / "images" / "scenes"
        plan = image_plan(sb, cfg)
        writer = prompt_writer or default_prompts
        prompts = cached_prompts(writer, sb, plan, media_dir / "images" / "prompts")
        approved = {
            slug: str(v["sheet_path"])
            for slug, v in (state.get("characters_approved") or {}).items()
            if isinstance(v, dict) and v.get("sheet_path")
        }
        by_name = {c.name: slugify(c.name) for c in sb.characters}
        budget = (state.get("options") or {}).get("budget_usd")
        spent = (state.get("cost") or {}).get("usd", 0.0)
        thread_id = _thread_id()

        def cancelled() -> bool:
            return bool(cancel_flags and thread_id and cancel_flags.is_set(thread_id))

        jobs = [
            Job(scene.id, k, prompts[scene.id][k])
            for scene in sb.scenes
            for k in range(plan[scene.id])
        ]

        def refs_of(job: Job) -> tuple[list[str], list[str]]:
            """(tên, đường dẫn sheet) của tối đa `scene_max_characters` nhân vật đã duyệt."""
            names: list[str] = []
            paths: list[str] = []
            for name in job.prompt.characters:
                slug = by_name.get(name)
                if slug in approved and len(names) < cfg.scene_max_characters:
                    names.append(name)
                    paths.append(approved[slug])
            return names, paths

        check = orientation_check if cfg.scene_orientation_check else None
        # Số lần tạo lại ảnh xoay còn được phép trong ngân sách (đặt sau khi chọn `todo`).
        retries = {"left": 0}
        retry_lock = threading.Lock()

        def take_retry() -> bool:
            with retry_lock:
                if budget is None:
                    return True
                if retries["left"] <= 0:
                    return False
                retries["left"] -= 1
                return True

        def attempt(
            body: str, seed: int, names: list[str], paths: list[str], path: Path, ids: list[str]
        ) -> tuple[bool, int, int]:
            """Tạo một ảnh và ghi `path`. Trả (thành công, số ảnh tính tiền, số ảnh bị xoay).

            Ảnh xoay được tạo lại một lần với seed khác; hết ngân sách thì giữ ảnh xoay."""
            data = [(media_dir / p).read_bytes() for p in paths if (media_dir / p).exists()]
            if len(data) < len(paths):  # thiếu file sheet thì bỏ tham chiếu, không đặt tên
                names, data = [], []
            billed = rotated = 0
            for extra in range(2):
                try:
                    img = provider.generate(
                        compose_prompt(sb.style_prompt_en, body, names),
                        seed=seed + extra,
                        width=cfg.scene_image_width,
                        height=cfg.scene_image_height,
                        on_submit=ids.append,
                        cancelled=cancelled,
                        reference_images=data,
                    )
                    payload = fit_9_16(img.data, cfg.scene_out_width, cfg.scene_out_height)
                except ImageAccountError:
                    raise  # không phải lỗi của ảnh: không đánh dấu `.blocked`, không đổi ẩn dụ
                except (ImageError, OSError):
                    return False, billed, rotated
                billed += 1
                if check is None or check(payload) != "rotated":
                    break
                rotated += 1
                log.warning("ảnh cảnh %s bị xoay ngang (seed %d)", path.name, seed + extra)
                if extra == 0 and not take_retry():
                    log.warning("hết ngân sách tạo lại, giữ ảnh xoay %s", path.name)
                    break
            else:
                return False, billed, rotated  # xoay cả hai lần: để nhánh ẩn dụ xử lý
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            return True, billed, rotated

        def rel(p: Path) -> str:
            return p.relative_to(media_dir).as_posix()

        def make(job: Job) -> Result:
            seed = base_seed(f"{sb.book.title}|{job.scene_id}|{job.ref}")
            names, paths = refs_of(job)
            key = cache_key(job.prompt.prompt_en, seed, paths, cfg)
            path = out_dir / f"{key}.jpg"
            blocked = out_dir / f"{key}.blocked"
            ids: list[str] = []
            if path.exists():
                return Result(rel(path), job.prompt.prompt_en, ids, 0)
            billed = rotated = 0
            if not blocked.exists():
                ok, billed, rotated = attempt(job.prompt.prompt_en, seed, names, paths, path, ids)
                if ok:
                    return Result(rel(path), job.prompt.prompt_en, ids, billed, rotated)
                log.warning(
                    "ảnh cảnh %s/%s bị chặn, lỗi hoặc xoay, đổi sang cảnh ẩn dụ",
                    job.scene_id,
                    job.ref,
                )
                if not rotated:  # xoay không phải do prompt: lần sau vẫn thử prompt chính
                    blocked.parent.mkdir(parents=True, exist_ok=True)
                    blocked.touch()
            mkey = cache_key(job.prompt.metaphor_en, seed, [], cfg)
            mpath = out_dir / f"{mkey}.jpg"
            if mpath.exists():
                return Result(rel(mpath), job.prompt.metaphor_en, ids, billed, rotated)
            ok, mbilled, mrotated = attempt(job.prompt.metaphor_en, seed, [], [], mpath, ids)
            billed, rotated = billed + mbilled, rotated + mrotated
            if ok:
                return Result(rel(mpath), job.prompt.metaphor_en, ids, billed, rotated)
            return Result(None, job.prompt.prompt_en, ids, billed, rotated)

        # Chỉ tạo số ảnh mới mà ngân sách còn cho phép; ảnh đã có trên đĩa không tốn tiền.
        def is_cached(job: Job) -> bool:
            seed = base_seed(f"{sb.book.title}|{job.scene_id}|{job.ref}")
            _, paths = refs_of(job)
            return (out_dir / f"{cache_key(job.prompt.prompt_en, seed, paths, cfg)}.jpg").exists()

        todo = jobs
        over_budget = False
        if budget is not None:
            pending = [j for j in jobs if not is_cached(j)]
            affordable = max(int((budget - spent + 1e-9) // cfg.price_image_usd), 0)
            if affordable < len(pending):
                over_budget = True
                skip = {(j.scene_id, j.ref) for j in pending[affordable:]}
                todo = [j for j in jobs if (j.scene_id, j.ref) not in skip]
            retries["left"] = max(affordable - len(pending), 0)

        results: dict[tuple[int, int], Result] = {}
        cancel_hit = False
        stop = AccountStop()
        with ThreadPoolExecutor(max_workers=cfg.fal_concurrency) as pool:
            futures = [(j, pool.submit(stop.guard, partial(make, j))) for j in todo]
            for job, fut in futures:
                try:
                    results[(job.scene_id, job.ref)] = fut.result()
                except Cancelled:
                    cancel_hit = True
                except ImageAccountError:
                    pass

        # Ảnh hỏng cả hai lần thì mượn ảnh gần nhất đã có (cùng cảnh trước, rồi các cảnh khác).
        order = [(j.scene_id, j.ref) for j in jobs]
        paths_by_slot: dict[tuple[int, int], str] = {
            slot: r.rel for slot, r in results.items() if r.rel
        }
        # Tài khoản Fal bị từ chối thì không mượn: node dừng để chạy lại sau khi nạp tiền.
        for i, slot in enumerate(order if not stop.hit else []):
            if slot in paths_by_slot or slot not in results:
                continue
            near = sorted(paths_by_slot, key=lambda s: abs(order.index(s) - i))
            if near:
                paths_by_slot[slot] = paths_by_slot[near[0]]
                log.warning("ảnh cảnh %s/%s lỗi, dùng lại ảnh gần nhất", *slot)

        asset_refs = {f"image:{sid}:{ref}": p for (sid, ref), p in paths_by_slot.items()}
        job_ids: dict[str, str] = {}
        for (sid, ref), r in results.items():
            if r.job_ids:
                job_ids[f"image:{sid}:{ref}"] = r.job_ids[-1]
        billed_total = sum(r.billed for r in results.values())
        rotated_total = sum(r.rotated for r in results.values())
        for scene in sb.scenes:
            scene.images = [
                SceneImage(
                    prompt_en=results[(scene.id, k)].prompt_en
                    if (scene.id, k) in results
                    else prompts[scene.id][k].prompt_en,
                    path=paths_by_slot.get((scene.id, k)),
                )
                for k in range(plan[scene.id])
            ]
        update: NodeUpdate = {
            "storyboard": sb.model_dump(mode="json"),
            "asset_refs": asset_refs,
            "fal_job_ids": job_ids,
            "cost": {
                "usd": billed_total * cfg.price_image_usd,
                "images": float(billed_total),
                "rotated_images": float(rotated_total),
            },
        }
        if cancel_hit:
            return {**update, "status": "cancelled", "error_code": ErrorCode.CANCELLED.value}
        if stop.hit:
            return {**update, "status": "failed", "error_code": ErrorCode.PROVIDER_QUOTA.value}
        if over_budget:
            return {**update, "status": "failed", "error_code": ErrorCode.BUDGET_EXCEEDED.value}
        if len(paths_by_slot) < len(jobs):
            return {
                **update,
                "status": "failed",
                "error_code": ErrorCode.PROVIDER_UNAVAILABLE.value,
            }
        return update

    return scene_images
