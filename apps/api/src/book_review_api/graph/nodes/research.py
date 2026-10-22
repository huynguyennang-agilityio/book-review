"""Node `research_agent` và `identify_confirm` (ngày 9)."""

from typing import Any

from langgraph.types import interrupt

from book_review_api.agents.research import ResearchRunner
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.nodes.precheck import fold
from book_review_api.graph.state import BookReviewState


def make_research_node(runner: ResearchRunner) -> NodeFn:
    @node
    def research_agent(state: BookReviewState) -> NodeUpdate:
        return runner(state["book"])

    return research_agent


def author_matches(wanted: str, found: Any) -> bool:
    """Khớp không dấu, không phân biệt hoa thường; chấp nhận tên đầy đủ chứa tên người nhập."""
    a, b = fold(wanted), fold(str(found or ""))
    return bool(a and b and (a in b or b in a))


def apply_author(research: dict[str, Any], author: str | None) -> tuple[dict[str, Any], bool]:
    """Ưu tiên ứng viên khớp tác giả. Trả (research đã chỉnh, có cảnh báo không khớp)."""
    if not author:
        return research, False
    pool = research.get("candidates") or [research["book"]]
    matched = [c for c in pool if author_matches(author, c.get("author"))]
    if matched:
        # Một ứng viên khớp thì tự chọn, không hỏi lại.
        if len(matched) == 1:
            return {
                **research,
                "book": matched[0],
                "candidates": [],
                "low_confidence": False,
            }, False
        return {**research, "candidates": matched}, False
    return research, True


def needs_confirmation(research: dict[str, Any]) -> bool:
    return bool(research.get("low_confidence")) or len(research.get("candidates") or []) > 1


@node
def identify_confirm(state: BookReviewState) -> NodeUpdate:
    """Trùng tên hoặc không chắc thì hỏi người dùng chọn đúng cuốn.

    Giá trị resume: `{"index": i}` chọn ứng viên thứ i, hoặc `{"cancel": true}`.
    """
    research = state.get("research")
    if not research:
        return {}
    author = state["book"].get("author")
    research, mismatch = apply_author(research, author)
    if mismatch:
        research = {**research, "low_confidence": True}
    elif not needs_confirmation(research):
        return {"research": research} if author else {}
    candidates = research.get("candidates") or [research["book"]]
    decision = interrupt(
        {
            "type": "identify_confirm",
            "message": (
                f"Không thấy cuốn nào của tác giả {author}. Chọn đúng cuốn bạn muốn."
                if mismatch
                else "Có nhiều cuốn trùng tên, chọn đúng cuốn bạn muốn."
            ),
            "candidates": candidates,
        }
    )
    if isinstance(decision, dict) and decision.get("cancel"):
        return {"status": "cancelled", "error_code": ErrorCode.CANCELLED.value}
    index = decision.get("index") if isinstance(decision, dict) else None
    if not isinstance(index, int) or not 0 <= index < len(candidates):
        return {"status": "failed", "error_code": ErrorCode.VALIDATION_ERROR.value}
    return {"research": {**research, "book": candidates[index], "low_confidence": False}}
