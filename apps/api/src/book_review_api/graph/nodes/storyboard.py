"""Node `storyboard` (ngày 10)."""

from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.storyboard.runner import StoryboardRunner


def make_storyboard_node(runner: StoryboardRunner) -> NodeFn:
    @node
    def storyboard(state: BookReviewState) -> NodeUpdate:
        research = state.get("research")
        if not research:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        return runner(research)

    return storyboard
