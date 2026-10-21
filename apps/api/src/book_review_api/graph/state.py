"""BookReviewState: state của graph `book_review`, lưu trong checkpoint sau mỗi node.

Các trường do nhiều nhánh song song cùng ghi (sau `review_script`) phải có reducer.
Cấu trúc chi tiết của `research`, `storyboard`, `timeline` có từ ngày 6 trở đi.
"""

from typing import Annotated, Any, Literal, NotRequired, TypedDict

Status = Literal["running", "done", "failed", "cancelled", "rejected"]

# Trạng thái kết thúc: node sau không chạy nữa.
TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "failed", "cancelled", "rejected"})


class BookInput(TypedDict):
    title: str
    author: NotRequired[str | None]


class RunOptions(TypedDict, total=False):
    """Tuỳ chọn người dùng chọn ở màn nhập sách (ngày 14); các node sau đọc dần."""

    minutes: int
    no_spoiler: bool
    voice: str
    budget_usd: float


def merge_dicts(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    return {**(left or {}), **(right or {})}


def add_costs(left: dict[str, float] | None, right: dict[str, float] | None) -> dict[str, float]:
    total = dict(left or {})
    for key, value in (right or {}).items():
        total[key] = total.get(key, 0.0) + value
    return total


def merge_status(left: Status | None, right: Status | None) -> Status | None:
    # Một nhánh đã huỷ/lỗi thì nhánh song song không ghi đè lại thành "running".
    if left in TERMINAL_STATUSES and right not in TERMINAL_STATUSES:
        return left
    return right


class BookReviewState(TypedDict, total=False):
    book: BookInput
    options: RunOptions
    research: dict[str, Any] | None
    storyboard: dict[str, Any] | None
    timeline: dict[str, Any] | None
    # Chỉ lưu đường dẫn object storage, không lưu binary.
    asset_refs: Annotated[dict[str, str], merge_dicts]
    fal_job_ids: Annotated[dict[str, str], merge_dicts]
    # usd, input_tokens, output_tokens... cộng dồn.
    cost: Annotated[dict[str, float], add_costs]
    eval_scores: Annotated[dict[str, float], merge_dicts]
    # Ước tính chi phí media trước checkpoint duyệt kịch bản (`storyboard.cost`).
    cost_estimate: dict[str, float] | None
    status: Annotated[Status | None, merge_status]
    # Mã lỗi trong `errors.ErrorCode` khi status là failed/rejected/cancelled.
    error_code: str | None
    cancel_requested: bool
