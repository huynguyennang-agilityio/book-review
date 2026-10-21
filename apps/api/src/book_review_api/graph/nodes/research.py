"""Node `research_agent` và `identify_confirm` (ngày 9)."""

from typing import Any

from langgraph.types import interrupt

from book_review_api.agents.research import ResearchRunner
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState


def make_research_node(runner: ResearchRunner) -> NodeFn:
    @node
    def research_agent(state: BookReviewState) -> NodeUpdate:
        return runner(state["book"])

    return research_agent


def needs_confirmation(research: dict[str, Any]) -> bool:
    return bool(research.get("low_confidence")) or len(research.get("candidates") or []) > 1


@node
def identify_confirm(state: BookReviewState) -> NodeUpdate:
    """Trùng tên hoặc không chắc thì hỏi người dùng chọn đúng cuốn.

    Giá trị resume: `{"index": i}` chọn ứng viên thứ i, hoặc `{"cancel": true}`.
    """
    research = state.get("research")
    if not research or not needs_confirmation(research):
        return {}
    candidates = research.get("candidates") or [research["book"]]
    decision = interrupt(
        {
            "type": "identify_confirm",
            "message": "Có nhiều cuốn trùng tên, chọn đúng cuốn bạn muốn.",
            "candidates": candidates,
        }
    )
    if isinstance(decision, dict) and decision.get("cancel"):
        return {"status": "cancelled", "error_code": ErrorCode.CANCELLED.value}
    index = decision.get("index") if isinstance(decision, dict) else None
    if not isinstance(index, int) or not 0 <= index < len(candidates):
        return {"status": "failed", "error_code": ErrorCode.VALIDATION_ERROR.value}
    return {"research": {**research, "book": candidates[index], "low_confidence": False}}
