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
    # Màn duyệt cần đủ storyboard, nguồn trích dẫn (trong từng cảnh), điểm và chi phí.
    storyboard = state.get("storyboard") or {}
    flagged = [
        s["id"]
        for s in storyboard.get("scenes", [])
        if ErrorCode.LOW_FAITHFULNESS in s.get("flags", [])
    ]
    return _wait_for_user(
        {
            "type": "review_script",
            "message": "Duyệt kịch bản trước khi dựng video.",
            "storyboard": state.get("storyboard"),
            "sources": _sources(storyboard),
            "eval_scores": state.get("eval_scores") or {},
            "low_faithfulness_scenes": flagged,
            "cost": state.get("cost") or {},
            "cost_estimate": state.get("cost_estimate") or {},
        }
    )


def _sources(storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    """Danh sách nguồn được trích, mỗi nguồn kèm id các cảnh dùng nó."""
    by_source: dict[str, list[int]] = {}
    for scene in storyboard.get("scenes", []):
        for c in scene.get("citations", []):
            ids = by_source.setdefault(c["source_id"], [])
            if scene["id"] not in ids:
                ids.append(scene["id"])
    return [{"source_id": k, "scene_ids": v} for k, v in by_source.items()]


@node
def review_characters(state: BookReviewState) -> NodeUpdate:
    return _wait_for_user({"type": "review_characters", "message": "Chọn ảnh cho từng nhân vật."})
