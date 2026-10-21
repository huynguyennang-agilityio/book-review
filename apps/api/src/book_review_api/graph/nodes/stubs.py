"""Node chưa làm: chỉ kiểm tra huỷ rồi đi tiếp. Mỗi node thay bằng bản thật theo plan từng ngày."""

from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState


def stub(name: str) -> NodeFn:
    def run(state: BookReviewState) -> NodeUpdate:
        return {}

    run.__name__ = run.__qualname__ = name
    return node(run)


@node
def save_memory(state: BookReviewState) -> NodeUpdate:
    # Node cuối: bản thật ghi Store ở ngày 20.
    return {"status": "done"}
