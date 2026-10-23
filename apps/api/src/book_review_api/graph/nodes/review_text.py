"""Tab "Từ bài review có sẵn": kiểm tra bài review người dùng dán và node `ingest_review`.

Bài có 3 ô: hook (tuỳ chọn), ý chính (bắt buộc), nhận xét (tuỳ chọn). Lời đọc giữ nguyên văn
nên thời lượng video suy từ độ dài bài; `precheck` chặn bài quá ngắn hoặc quá dài trước khi tốn
tiền. Xem `docs/plan/review-text/`.
"""

from collections.abc import Mapping
from typing import Any

from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.nodes.precheck import find_excluded_keyword
from book_review_api.graph.state import BookReviewState, UserReview
from book_review_api.rag.ingest import normalize_text
from book_review_api.rag.pii import mask_pii
from book_review_api.storyboard.duration import count_syllables, estimate_seconds

MIN_MAIN_WORDS = 100
MAX_SECONDS = 300.0
# Hook dài hơn ~5 giây thì cảnh báo, không chặn.
HOOK_MAX_WORDS = 20
# Giới hạn cứng mỗi ô để không nhận văn bản khổng lồ (5 phút đọc chỉ ~1.100 từ).
MAX_FIELD_CHARS = 20_000
FIELDS = ("hook", "main", "comment")


class ReviewInputError(ValueError):
    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def is_user_review(state: Mapping[str, Any]) -> bool:
    return (state.get("options") or {}).get("source") == "user_review"


def _clean(text: object) -> tuple[str | None, int]:
    if not isinstance(text, str):
        return None, 0
    masked = mask_pii(normalize_text(text[:MAX_FIELD_CHARS]))
    return masked.text or None, masked.total


def clean_user_review(raw: Mapping[str, Any] | None) -> UserReview:
    """Làm sạch và che PII ba ô, kiểm độ dài. Lỗi thì ném `ReviewInputError` với mã lỗi."""
    if not isinstance(raw, Mapping):
        raise ReviewInputError(ErrorCode.VALIDATION_ERROR)
    cleaned: dict[str, str | None] = {}
    pii = 0
    for field in FIELDS:
        cleaned[field], found = _clean(raw.get(field))
        pii += found
    main = cleaned["main"]
    if not main or count_syllables(main) < MIN_MAIN_WORDS:
        raise ReviewInputError(ErrorCode.REVIEW_TOO_SHORT)
    if review_seconds(cleaned) > MAX_SECONDS:
        raise ReviewInputError(ErrorCode.REVIEW_TOO_LONG)
    warnings: list[str] = []
    if cleaned["hook"] and count_syllables(cleaned["hook"]) > HOOK_MAX_WORDS:
        warnings.append("HOOK_LONG")
    return UserReview(
        hook=cleaned["hook"],
        main=main,
        comment=cleaned["comment"],
        warnings=warnings,
        pii_masked=pii,
    )


def review_seconds(review: Mapping[str, str | None]) -> float:
    """Thời lượng đọc ước tính của cả bài (mỗi ô tính như một cảnh)."""
    return estimate_seconds(t for f in FIELDS if (t := review.get(f)))


def excluded_keyword(review: Mapping[str, Any]) -> str | None:
    """Từ khoá thể loại không hỗ trợ (tiên hiệp, kiếm hiệp...) trong nội dung bài."""
    for field in FIELDS:
        text = review.get(field)
        if isinstance(text, str) and (found := find_excluded_keyword(text)):
            return found
    return None


def precheck_review(state: BookReviewState) -> NodeUpdate:
    """Phần kiểm tra riêng của tab review, gọi từ `precheck`. Rỗng nghĩa là hợp lệ, không đổi."""
    try:
        review = clean_user_review(state.get("user_review"))
    except ReviewInputError as e:
        return {"status": "rejected", "error_code": e.code.value}
    if excluded_keyword(review):
        return {"status": "rejected", "error_code": ErrorCode.GENRE_EXCLUDED.value}
    return {"user_review": review}


def make_ingest_review_node() -> NodeFn:
    """Ngày 3 làm thật: chia cảnh nguyên văn, nạp RAG, metadata. Hiện chỉ đi tiếp."""

    @node
    def ingest_review(state: BookReviewState) -> NodeUpdate:
        return {}

    return ingest_review
