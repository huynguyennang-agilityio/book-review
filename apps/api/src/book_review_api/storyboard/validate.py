"""Kiểm tra citation của storyboard: cảnh dữ kiện có trích dẫn, quote có thật trong chunk."""

import re
import unicodedata
from collections.abc import Mapping

from book_review_api.rag.retrieve import Chunk
from book_review_api.storyboard.schema import (
    CITED_SECTIONS,
    MAX_QUOTE_CHARS,
    Scene,
    Storyboard,
)

_SPACE_RE = re.compile(r"\s+")
_QUOTE_MAP: dict[int, str | int | None] = {
    ord("“"): '"',
    ord("”"): '"',
    ord("‘"): "'",
    ord("’"): "'",
    ord("…"): "...",
}


def fold_quote(text: str) -> str:
    """Chuẩn hoá để so khớp quote: NFC, gộp khoảng trắng, thống nhất dấu nháy, bỏ hoa/thường."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_QUOTE_MAP)
    return _SPACE_RE.sub(" ", text).strip().casefold()


def scene_problems(scene: Scene, chunks: Mapping[str, Chunk]) -> list[str]:
    """Danh sách lỗi của một cảnh (rỗng nếu hợp lệ), viết để đưa lại cho model sửa."""
    problems: list[str] = []
    if scene.section in CITED_SECTIONS and not scene.citations:
        problems.append(f"Cảnh {scene.id} ({scene.section}) thiếu citation.")
    for c in scene.citations:
        chunk = chunks.get(c.chunk_id)
        if chunk is None:
            problems.append(f"Cảnh {scene.id}: chunk_id {c.chunk_id!r} không có trong nguồn.")
            continue
        if chunk.metadata.get("source_id") != c.source_id:
            problems.append(f"Cảnh {scene.id}: source_id không khớp với chunk {c.chunk_id!r}.")
        if not c.quote.strip():
            problems.append(f"Cảnh {scene.id}: quote trống.")
        elif len(c.quote) > MAX_QUOTE_CHARS:
            problems.append(f"Cảnh {scene.id}: quote dài {len(c.quote)} ký tự (tối đa 200).")
        elif fold_quote(c.quote) not in fold_quote(chunk.content):
            problems.append(f"Cảnh {scene.id}: quote không có nguyên văn trong chunk.")
    return problems


def storyboard_problems(sb: Storyboard, chunks: Mapping[str, Chunk]) -> list[str]:
    problems = [p for scene in sb.scenes for p in scene_problems(scene, chunks)]
    ids = [s.id for s in sb.scenes]
    if len(set(ids)) != len(ids):
        problems.append("Có id cảnh bị trùng.")
    return problems
