"""Điểm dừng chờ người dùng duyệt (interrupt). Giao diện duyệt làm ở ngày 11 và 15.

Giá trị resume là dict; `{"cancel": true}` huỷ luôn project từ màn hình duyệt. Huỷ bằng
`update_state` không dùng được khi hai nhánh song song cùng đang chờ (LangGraph báo
"Ambiguous update"), nên đường huỷ khi đang chờ duyệt đi qua giá trị resume.
"""

from typing import Any

from langgraph.types import interrupt

from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeUpdate, node
from book_review_api.graph.state import BookReviewState


def _wait_for_user(payload: dict[str, Any]) -> NodeUpdate:
    decision = interrupt(payload)
    if isinstance(decision, dict) and decision.get("cancel"):
        return {"status": "cancelled", "error_code": ErrorCode.CANCELLED.value}
    return {}


@node
def review_script(state: BookReviewState) -> NodeUpdate:
    return _wait_for_user(
        {"type": "review_script", "message": "Duyệt kịch bản trước khi dựng video."}
    )


@node
def review_characters(state: BookReviewState) -> NodeUpdate:
    return _wait_for_user({"type": "review_characters", "message": "Chọn ảnh cho từng nhân vật."})
