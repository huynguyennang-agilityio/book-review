"""Endpoint AG-UI `/agent` (ngày 14). Bọc `ag-ui-langgraph` trong một module để dễ thay thư viện
(spike ngày 2, lỗi 3 và 4).

Mỗi request phải có JWT hợp lệ và `thread_id` phải là của một project thuộc người gửi (RLS lọc),
nếu không trả 404 như project không tồn tại. Event stream gồm tiến độ node (STEP_*), tool call,
state, interrupt (RUN_FINISHED outcome=interrupt) và event tuỳ biến `source` cho danh sách nguồn.
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StateSnapshot

from book_review_api.auth import CurrentUser, current_user
from book_review_api.config import get_settings
from book_review_api.db import ensure_local_user, user_transaction
from book_review_api.errors import AppError, ErrorCode
from book_review_api.prompt_loader import prompt_version_label, prompt_versions

log = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

AGENT_NAME = "review"


def make_agent(graph: CompiledStateGraph[Any]) -> LangGraphAgent:
    return LangGraphAgent(
        name=AGENT_NAME,
        graph=graph,
        description="Agent review sách",
        # Run kết thúc bằng RUN_FINISHED outcome=interrupt; client resume qua RunAgentInput.resume.
        emit_interrupt_outcome=True,
    )


async def _set_status(request: Request, user: CurrentUser, thread_id: str, status: str) -> None:
    async with user_transaction(request.app.state.app_pool, user) as conn:
        await conn.execute(
            # Huỷ là trạng thái cuối: stream còn chạy dở không được ghi đè lại.
            "update public.projects set status = %s, updated_at = now()"
            " where thread_id = %s and status <> 'cancelled'",
            [status, thread_id],
        )


_TERMINAL = {"done", "failed", "cancelled", "rejected"}


def _check_budget(budget_usd: Any, spent: float) -> float:
    """Ngân sách mới khi chạy lại: số dương, lớn hơn số đã tiêu, không quá trần."""
    cap = get_settings().max_budget_usd
    if isinstance(budget_usd, bool) or not isinstance(budget_usd, int | float):
        raise AppError(ErrorCode.VALIDATION_ERROR, "Ngân sách phải là một số.")
    if budget_usd <= spent:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Ngân sách mới phải lớn hơn số đã tiêu (${spent:.2f}).",
        )
    if budget_usd > cap:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Ngân sách tối đa là ${cap:.0f}.")
    return float(budget_usd)


async def _rewind_failed(
    graph: CompiledStateGraph[Any], thread_id: str, budget_usd: Any = None
) -> None:
    """Chạy lại project lỗi từ node vừa lỗi: tạo checkpoint mới từ lần checkpoint cuối cùng còn
    đang chạy (trước khi status chuyển sang `failed`), nên các bước đã xong không chạy lại.

    Checkpoint mới giữ chi phí đã tiêu trong lần lỗi (tua lại không làm mất tiền đã trả) và, nếu
    có, ngân sách mới người dùng nhập."""
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    latest: Any = None
    failed: Any = None
    async for snap in graph.aget_state_history(config):
        latest = latest or snap
        # Chi phí cần giữ lấy từ state lỗi mới nhất: checkpoint mới nhất có thể là bản chép do một
        # lần chạy lại hỏng để lại, mang chi phí cũ hơn.
        if failed is None and snap.values.get("status") == "failed":
            failed = snap
        if not snap.next or str(snap.values.get("status") or "") in _TERMINAL:
            continue
        # Bỏ qua checkpoint do các lần chạy lại trước ghi (`update`, `fork`): node nào ghi ra
        # chúng không còn trong `parent.next`, và chạy lại lần hai phải tua về đúng chỗ graph dừng.
        if (snap.metadata or {}).get("source") not in (None, "loop"):
            continue
        spent = dict((failed or latest).values.get("cost") or {})
        update: dict[str, Any] = {}
        if budget_usd is not None:
            budget = _check_budget(budget_usd, float(spent.get("usd", 0.0)))
            update["options"] = {**(snap.values.get("options") or {}), "budget_usd": budget}
        before = snap.values.get("cost") or {}
        delta = {k: v - before.get(k, 0.0) for k, v in spent.items() if v != before.get(k, 0.0)}
        if delta:
            # `cost` cộng dồn (reducer `add_costs`) nên chỉ ghi phần chênh.
            update["cost"] = delta
        if update and await _update_as_writer(graph, snap, update):
            return
        # `__copy__` chép nguyên checkpoint; không ghi thay node nào, nên không lỗi "Ambiguous
        # update" khi bước trước có nhiều node chạy song song (subtitles, review_characters).
        # Cũng là checkpoint mới nhất, thay cho các lần ghi thử hỏng ở trên.
        await graph.aupdate_state(snap.config, None, as_node="__copy__")
        if "options" in update:
            raise AppError(ErrorCode.INVALID_STATE, "Không đổi được ngân sách cho project này.")
        return
    raise AppError(ErrorCode.NOT_FOUND)


async def _update_as_writer(
    graph: CompiledStateGraph[Any], snap: StateSnapshot, update: dict[str, Any]
) -> bool:
    """Ghi `update` vào bản sao của `snap` như thể do một trong các node vừa tạo ra nó ghi.

    `__copy__` bỏ qua giá trị, nên phải ghi thay một node; chọn node trong `parent.next` (node
    vừa chạy ra checkpoint này) mà sau khi ghi các node chờ chạy vẫn y như cũ."""
    if snap.parent_config is None:
        return False
    parent = await graph.aget_state(snap.parent_config)
    for writer in parent.next:
        new_config = await graph.aupdate_state(snap.config, update, as_node=writer)
        if (await graph.aget_state(new_config)).next == snap.next:
            return True
        log.warning("chạy lại: ghi thay %s làm đổi node chờ chạy, thử node khác", writer)
    return False


async def _final_status(graph: CompiledStateGraph[Any], thread_id: str) -> str:
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    if snap.next and any(t.interrupts for t in snap.tasks):
        return "awaiting_review"
    status = str(snap.values.get("status") or "")
    return status if status in {"done", "failed", "cancelled", "rejected"} else "done"


@router.post("/agent")
async def agent_endpoint(
    input_data: RunAgentInput,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> StreamingResponse:
    await ensure_local_user(request.app.state.app_pool, user)
    async with user_transaction(request.app.state.app_pool, user) as conn:
        cur = await conn.execute(
            "select id, status from public.projects where thread_id = %s", [input_data.thread_id]
        )
        row = await cur.fetchone()
        if row is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if row["status"] == "cancelled":
            raise AppError(ErrorCode.CANCELLED)
        failed_before = row["status"] == "failed"
        project_id = row["id"]
    if failed_before:
        props = input_data.forwarded_props
        budget_usd = props.get("budget_usd") if isinstance(props, dict) else None
        await _rewind_failed(request.app.state.graph, input_data.thread_id, budget_usd)
        # Checkpoint mới còn node chưa chạy; lệnh resume giả buộc ag-ui-langgraph chạy tiếp
        # chúng thay vì bắt đầu run mới từ đầu.
        input_data.forwarded_props = {"command": {"resume": "true"}}
    await _set_status(request, user, input_data.thread_id, "running")
    encoder = EventEncoder(accept=request.headers.get("accept", "text/event-stream"))
    # Mỗi request một bản sao: LangGraphAgent giữ state của run hiện tại trong self.active_run.
    agent = request.app.state.agent.clone()
    # user_id cho node đọc/ghi bộ nhớ; metadata ghi version prompt vào run LangSmith.
    agent.config = {
        "configurable": {"user_id": user.user_id, "project_id": str(project_id)},
        "metadata": {
            "prompt_version": prompt_version_label(),
            "prompt_versions": prompt_versions(),
        },
    }
    graph: CompiledStateGraph[Any] = request.app.state.graph

    async def stream() -> AsyncIterator[str]:
        try:
            async for event in agent.run(input_data):
                yield encoder.encode(event)
        finally:
            try:
                await _set_status(
                    request,
                    user,
                    input_data.thread_id,
                    await _final_status(graph, input_data.thread_id),
                )
            except Exception:  # noqa: BLE001
                log.exception("không cập nhật được status project")

    return StreamingResponse(stream(), media_type=encoder.get_content_type())
