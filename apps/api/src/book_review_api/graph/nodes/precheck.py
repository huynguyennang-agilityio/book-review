"""Node `precheck`: chặn sớm thể loại không hỗ trợ theo từ khoá trong tên sách, không gọi API.

Chỉ bắt được tên sách có chữ thể loại hoặc tên tác phẩm nổi tiếng. Phân loại theo nội dung
do `GenreGuardMiddleware` của research agent làm (ngày 9).
"""

import re
import unicodedata

from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeUpdate, node
from book_review_api.graph.state import BookReviewState

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


@node
def precheck(state: BookReviewState) -> NodeUpdate:
    if find_excluded_keyword(state["book"]["title"]):
        return {"status": "rejected", "error_code": ErrorCode.GENRE_EXCLUDED.value}
    return {"status": "running", "error_code": None}
