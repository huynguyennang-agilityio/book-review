"""Phần dùng chung của các node: kiểm tra huỷ và bỏ qua khi graph đã kết thúc."""

from functools import wraps
from typing import Any, Protocol

from book_review_api.errors import ErrorCode
from book_review_api.graph.state import TERMINAL_STATUSES, BookReviewState

NodeUpdate = dict[str, Any]


class NodeFn(Protocol):
    def __call__(self, state: BookReviewState) -> NodeUpdate: ...


class Cancelled(Exception):
    """Người dùng đã yêu cầu huỷ."""


def check_cancel(state: BookReviewState) -> None:
    """Gọi đầu mỗi node. Ném `Cancelled` nếu người dùng đã yêu cầu huỷ."""
    if state.get("cancel_requested"):
        raise Cancelled


def node(fn: NodeFn) -> NodeFn:
    """Bọc node: gọi `check_cancel` trước, ghi status `cancelled` vào state thay vì làm sập graph.

    Node ở điểm hợp nhánh (vd `motion`) vẫn được gọi khi một nhánh đã kết thúc, nên status
    kết thúc cũng làm node bỏ qua.
    """

    @wraps(fn)
    def wrapper(state: BookReviewState) -> NodeUpdate:
        if state.get("status") in TERMINAL_STATUSES:
            return {}
        try:
            check_cancel(state)
            return fn(state)
        except Cancelled:
            return {"status": "cancelled", "error_code": ErrorCode.CANCELLED.value}

    return wrapper
