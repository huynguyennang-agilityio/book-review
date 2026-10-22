"""Node `precheck`: chặn sớm thể loại không hỗ trợ theo từ khoá trong tên sách, không gọi API.

Chỉ bắt được tên sách có chữ thể loại hoặc tên tác phẩm nổi tiếng. Phân loại theo nội dung
do `GenreGuardMiddleware` của research agent làm (ngày 9).
"""

import logging
import re
import unicodedata

from langgraph.config import get_config, get_store

from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.memory.store import apply_preferences, load_preferences

log = logging.getLogger(__name__)

# Thể loại bị loại trừ (mục 1 plan v5) và vài tác phẩm tiêu biểu. Viết có dấu, so khớp
# sau khi bỏ dấu để bắt cả tên gõ không dấu.
EXCLUDED_KEYWORDS: tuple[str, ...] = (
    "tiên hiệp",
    "kiếm hiệp",
    "huyền huyễn",
    "tu tiên",
    "võ hiệp",
    "tu chân",
    "anh hùng xạ điêu",
    "thần điêu hiệp lữ",
    "ỷ thiên đồ long ký",
    "thiên long bát bộ",
    "tiếu ngạo giang hồ",
    "lộc đỉnh ký",
    "phàm nhân tu tiên",
    "đấu phá thương khung",
    "tru tiên",
)


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt, gộp khoảng trắng: "Kiếm  Hiệp" -> "kiem hiep"."""
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(re.findall(r"\w+", text))


_PATTERN = re.compile(r"\b(" + "|".join(re.escape(fold(k)) for k in EXCLUDED_KEYWORDS) + r")\b")


def find_excluded_keyword(title: str) -> str | None:
    match = _PATTERN.search(fold(title))
    return match.group(1) if match else None


def _saved_preferences() -> dict[str, object]:
    """Sở thích đã lưu của người dùng đang chạy; rỗng nếu không có Store hay user_id."""
    try:
        store = get_store()
        user_id = get_config().get("configurable", {}).get("user_id")
    except RuntimeError:  # chạy ngoài graph (test, script)
        return {}
    if store is None or not user_id:
        return {}
    try:
        return load_preferences(store, str(user_id))
    except Exception:  # noqa: BLE001
        log.warning("không đọc được sở thích đã lưu", exc_info=True)
        return {}


MAX_AUTHOR_LEN = 100


def clean_author(author: str | None) -> str | None:
    """Cắt khoảng trắng thừa, giới hạn độ dài; rỗng thì coi như không nhập."""
    cleaned = " ".join((author or "").split())[:MAX_AUTHOR_LEN].strip()
    return cleaned or None


@node
def precheck(state: BookReviewState) -> NodeUpdate:
    if find_excluded_keyword(state["book"]["title"]):
        return {"status": "rejected", "error_code": ErrorCode.GENRE_EXCLUDED.value}
    update: NodeUpdate = {"status": "running", "error_code": None}
    book = state["book"]
    if "author" in book and clean_author(book["author"]) != book["author"]:
        update["book"] = {**book, "author": clean_author(book["author"])}
    options = dict(state.get("options") or {})
    prefs = _saved_preferences()
    if prefs:
        merged = apply_preferences(options, prefs)
        if applied := sorted(set(merged) - set(options)):
            update["options"] = merged
            update["preferences_applied"] = applied
    return update
