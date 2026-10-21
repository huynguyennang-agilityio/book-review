"""Node `faithfulness_eval` và `estimate_cost` (ngày 11)."""

from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.storyboard.cost import estimate_media_cost
from book_review_api.storyboard.faithfulness import FaithfulnessRunner
from book_review_api.storyboard.schema import Storyboard


def make_faithfulness_node(runner: FaithfulnessRunner) -> NodeFn:
    @node
    def faithfulness_eval(state: BookReviewState) -> NodeUpdate:
        storyboard = state.get("storyboard")
        if not storyboard:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        return runner(storyboard)

    return faithfulness_eval


def make_estimate_cost_node(settings: Settings | None = None) -> NodeFn:
    @node
    def estimate_cost(state: BookReviewState) -> NodeUpdate:
        storyboard = state.get("storyboard")
        if not storyboard:
            return {}
        sb = Storyboard.model_validate(storyboard)
        return {"cost_estimate": estimate_media_cost(sb, settings or get_settings())}

    return estimate_cost
