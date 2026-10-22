"""Node chưa làm: chỉ kiểm tra huỷ rồi đi tiếp. Mỗi node thay bằng bản thật theo plan từng ngày."""

import logging

from langgraph.config import get_config, get_store

from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.memory.store import record_run

log = logging.getLogger(__name__)


def stub(name: str) -> NodeFn:
    def run(state: BookReviewState) -> NodeUpdate:
        return {}

    run.__name__ = run.__qualname__ = name
    return node(run)


@node
def save_memory(state: BookReviewState) -> NodeUpdate:
    """Node cuối: ghi sở thích, lịch sử sách, nhân vật đã duyệt và phản hồi vào Store."""
    try:
        store = get_store()
    except RuntimeError:  # chạy không có Store (test khung, script)
        return {"status": "done"}
    config = get_config()
    user_id = config.get("configurable", {}).get("user_id")
    if store is not None and user_id:
        try:
            record_run(
                store,
                str(user_id),
                thread_id=str(config.get("configurable", {}).get("thread_id") or ""),
                book=state.get("book") or {},
                options=state.get("options") or {},
                characters=state.get("characters_approved") or {},
                feedback=state.get("feedback") or [],
            )
        except Exception:  # noqa: BLE001
            # Lỗi bộ nhớ không được làm hỏng video đã dựng xong.
            log.warning("không ghi được bộ nhớ", exc_info=True)
    return {"status": "done"}


@node
def regen_characters_stub(state: BookReviewState) -> NodeUpdate:
    # Không có provider ảnh: bỏ yêu cầu tạo lại để graph không lặp mãi ở màn duyệt.
    return {"character_regen": None}


@node
def manual_images_stub(state: BookReviewState) -> NodeUpdate:
    # Nhánh manual (tải ảnh lên) làm ở ngày 4. Tới lúc đó dừng hẳn để không rơi vào Fal.
    return {"status": "failed", "error_code": ErrorCode.INVALID_STATE.value}
