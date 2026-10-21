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
from langgraph.graph.state import CompiledStateGraph

from book_review_api.auth import CurrentUser, current_user
from book_review_api.db import ensure_local_user, user_transaction
from book_review_api.errors import AppError, ErrorCode

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
            "select status from public.projects where thread_id = %s", [input_data.thread_id]
        )
        row = await cur.fetchone()
        if row is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if row["status"] == "cancelled":
            raise AppError(ErrorCode.CANCELLED)
    await _set_status(request, user, input_data.thread_id, "running")
    encoder = EventEncoder(accept=request.headers.get("accept", "text/event-stream"))
    # Mỗi request một bản sao: LangGraphAgent giữ state của run hiện tại trong self.active_run.
    agent = request.app.state.agent.clone()
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
