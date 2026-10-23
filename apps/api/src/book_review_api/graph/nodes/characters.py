"""Node `character_sheets` (ngày 16): 4 ứng viên sheet nhiều góc cho mỗi nhân vật chính.

Nhân vật đã duyệt của cùng series nằm trong Store (`("characters", <series>)`, ghi ở ngày 17/20)
thì dùng lại, không tạo mới. Chi phí cộng vào `state.cost`; vượt `options.budget_usd` thì dừng
với `BUDGET_EXCEEDED`. Ảnh ghi vào `<media_dir>/characters/<job_key>/`, file đã có thì dùng lại.
"""

import hashlib
import logging
import re
import threading
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

from langgraph.config import get_config, get_store

from book_review_api.cancel import CancelFlags
from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import Cancelled, NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.providers.image_fal import ImageAccountError, ImageError, ImageProvider
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


def sheet_prompt(
    character: Character, style: str, n: int, safe: bool = False, note: str = ""
) -> str:
    description = SAFE_DESCRIPTION if safe else character.description_en.strip().rstrip(".")
    prompt = SHEET_PROMPT.format(description=description, style=style.strip().rstrip("."), n=n)
    # Ghi chú tạo lại của người dùng (đã cắt độ dài): đặt trước mệnh đề "no text".
    if note.strip() and not safe:
        prompt = prompt.replace(" no text,", f" Adjustment requested: {note.strip()}. no text,")
    return prompt


def generate_sheet(
    provider: ImageProvider,
    cfg: Settings,
    character: Character,
    style: str,
    path: Path,
    seed: int,
    n: int,
    media_dir: Path,
    cancelled: Callable[[], bool],
    note: str = "",
) -> tuple[str | None, str, bool]:
    """Một ảnh sheet: `(đường dẫn tương đối, fal job id, có tính tiền)`. File đã có thì dùng lại,
    không tốn tiền. Bị bộ lọc chặn thì thử lại một lần với mô tả trung tính."""
    if path.exists():
        return path.relative_to(media_dir).as_posix(), "", False
    job: list[str] = []
    for safe in (False, True):
        try:
            img = provider.generate(
                sheet_prompt(character, style, n, safe, note),
                seed=seed,
                width=cfg.character_sheet_width,
                height=cfg.character_sheet_height,
                on_submit=job.append,
                cancelled=cancelled,
            )
        except ImageAccountError:
            raise  # đổi sang mô tả trung tính không giúp gì khi tài khoản bị từ chối
        except ImageError:
            log.warning("ảnh nhân vật %s lỗi (safe=%s)", character.name, safe)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(img.data)
        return path.relative_to(media_dir).as_posix(), img.job_id, True
    return None, job[-1] if job else "", False


T = TypeVar("T")


class AccountStop:
    """Một job gặp lỗi tài khoản Fal thì các job chưa gửi bỏ qua luôn, không gọi Fal thêm."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def hit(self) -> bool:
        return self._event.is_set()

    def guard(self, fn: Callable[[], T]) -> T:
        if self.hit:
            raise ImageAccountError("bỏ qua: tài khoản Fal đã bị từ chối")
        try:
            return fn()
        except ImageAccountError:
            self._event.set()
            raise


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

        stop = AccountStop()

        def make(item: tuple[Character, str, int]) -> tuple[str, int, str | None, str, bool]:
            ch, slug, i = item
            path = out_dir / f"{slug}_{i}.jpg"
            rel, jid, billed = stop.guard(lambda: generate_sheet(
                provider, cfg, ch, sb.style_prompt_en, path, base_seed(ch.name) + i, i + 1,
                media_dir, cancelled,
            ))  # fmt: skip
            return slug, i, rel, jid, billed

        cancel_hit = False
        with ThreadPoolExecutor(max_workers=cfg.fal_concurrency) as pool:
            futures = [pool.submit(make, t) for t in todo]
            for fut in futures:
                try:
                    slug, i, rel, jid, billed = fut.result()
                except Cancelled:
                    cancel_hit = True
                    continue
                except ImageAccountError:
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
        if stop.hit:
            return {**update, "status": "failed", "error_code": ErrorCode.PROVIDER_QUOTA.value}
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


MAX_REGEN_ROUNDS = 3
MAX_NOTE_CHARS = 200


def make_regen_characters_node(
    provider: ImageProvider,
    settings: Settings | None = None,
    cancel_flags: CancelFlags | None = None,
) -> NodeFn:
    """Tạo lại 4 ứng viên cho các nhân vật người dùng yêu cầu ở màn duyệt (kèm ghi chú). Mỗi vòng
    ghi file riêng `<slug>_r<vòng>_<i>.jpg` nên chạy lại không tốn tiền. Tối đa `MAX_REGEN_ROUNDS`
    vòng mỗi nhân vật; vượt ngân sách thì giữ ứng viên cũ và dừng với `BUDGET_EXCEEDED`."""

    @node
    def regen_characters(state: BookReviewState) -> NodeUpdate:
        cfg = settings or get_settings()
        requests = state.get("character_regen") or {}
        storyboard_raw = state.get("storyboard")
        if not storyboard_raw:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        sb = Storyboard.model_validate(storyboard_raw)
        by_slug = {slugify(c.name): c for c in sb.characters[: cfg.character_max]}
        candidates = state.get("character_candidates") or {}
        media_dir = Path(cfg.media_dir)
        out_dir = media_dir / "characters" / job_key(sb, cfg)
        budget = (state.get("options") or {}).get("budget_usd")
        spent = (state.get("cost") or {}).get("usd", 0.0)
        thread_id = _thread_id()

        def cancelled() -> bool:
            return bool(cancel_flags and thread_id and cancel_flags.is_set(thread_id))

        todo: list[tuple[str, Character, int, str]] = []
        for slug, note in requests.items():
            entry = candidates.get(slug)
            ch = by_slug.get(slug)
            rnd = int(entry.get("round", 0)) + 1 if entry else 0
            if not entry or ch is None or entry.get("reused") or rnd > MAX_REGEN_ROUNDS:
                continue
            todo.append((slug, ch, rnd, str(note)[:MAX_NOTE_CHARS]))

        n = cfg.character_sheet_images
        affordable = (
            len(todo) * n
            if budget is None
            else max(int((budget - spent + 1e-9) // cfg.price_image_usd), 0)
        )
        over_budget = affordable < len(todo) * n
        todo = todo[: affordable // n]

        jobs = [(slug, ch, rnd, note, i) for slug, ch, rnd, note in todo for i in range(n)]

        stop = AccountStop()

        def make(
            job: tuple[str, Character, int, str, int],
        ) -> tuple[str, int, str | None, str, bool]:
            slug, ch, rnd, note, i = job
            rel, jid, billed = stop.guard(lambda: generate_sheet(
                provider, cfg, ch, sb.style_prompt_en, out_dir / f"{slug}_r{rnd}_{i}.jpg",
                base_seed(ch.name) + 100 * rnd + i, i + 1, media_dir, cancelled, note,
            ))  # fmt: skip
            return slug, i, rel, jid, billed

        images: dict[str, list[str | None]] = {slug: [None] * n for slug, *_ in todo}
        asset_refs: dict[str, str] = {}
        job_ids: dict[str, str] = {}
        billed_count = 0
        cancel_hit = False
        with ThreadPoolExecutor(max_workers=cfg.fal_concurrency) as pool:
            futures = [pool.submit(make, j) for j in jobs]
            for fut in futures:
                try:
                    slug, i, rel, jid, billed = fut.result()
                except Cancelled:
                    cancel_hit = True
                    continue
                except ImageAccountError:
                    continue
                images[slug][i] = rel
                if rel:
                    asset_refs[f"character:{slug}:{i}"] = rel
                if jid:
                    job_ids[f"character:{slug}:{i}"] = jid
                billed_count += int(billed)

        new_candidates: dict[str, Any] = {}
        for slug, _, rnd, _ in todo:
            got = [p for p in images[slug] if p]
            if got:  # tạo lại hỏng hết thì giữ ứng viên cũ
                new_candidates[slug] = {**candidates[slug], "images": got, "round": rnd}
        # Ứng viên cũ không còn hợp lệ nên bỏ lựa chọn tạm của nhân vật vừa tạo lại.
        picks = {k: v for k, v in (state.get("character_picks") or {}).items()
                 if k not in new_candidates}  # fmt: skip
        update: NodeUpdate = {
            "character_candidates": new_candidates,
            "character_picks": picks,
            "character_regen": None,
            "asset_refs": asset_refs,
            "fal_job_ids": job_ids,
            "cost": {"usd": billed_count * cfg.price_image_usd, "images": float(billed_count)},
        }
        if cancel_hit:
            return {**update, "status": "cancelled", "error_code": ErrorCode.CANCELLED.value}
        if stop.hit:
            return {**update, "status": "failed", "error_code": ErrorCode.PROVIDER_QUOTA.value}
        if over_budget:
            return {**update, "status": "failed", "error_code": ErrorCode.BUDGET_EXCEEDED.value}
        return update

    return regen_characters
