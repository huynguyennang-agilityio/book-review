"""Graph với AsyncPostgresSaver/Store thật: dừng ở interrupt, đóng hết kết nối (như restart
server), mở lại bằng pool và graph mới rồi resume tiếp cùng `thread_id`."""

import uuid

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command

from book_review_api.db import make_graph_pool
from book_review_api.graph.build import build_graph

pytestmark = pytest.mark.anyio


async def test_resume_after_restart(database_url: str) -> None:
    cfg: RunnableConfig = {"configurable": {"thread_id": f"it-{uuid.uuid4()}"}}

    pool = make_graph_pool(database_url)
    await pool.open()
    try:
        graph = build_graph(AsyncPostgresSaver(pool), AsyncPostgresStore(pool))
        await graph.ainvoke({"book": {"title": "Nhà giả kim"}}, cfg)
        assert (await graph.aget_state(cfg)).next == ("review_script",)
    finally:
        await pool.close()

    pool = make_graph_pool(database_url)
    await pool.open()
    try:
        graph = build_graph(AsyncPostgresSaver(pool), AsyncPostgresStore(pool))
        state = await graph.aget_state(cfg)
        assert state.next == ("review_script",)
        assert state.values["book"]["title"] == "Nhà giả kim"
        await graph.ainvoke(Command(resume={"approved": True}), cfg)
        assert (await graph.aget_state(cfg)).next == ("choose_image_mode",)
        await graph.ainvoke(Command(resume={"mode": "auto"}), cfg)
        assert (await graph.aget_state(cfg)).next == ("review_characters",)
        await graph.ainvoke(Command(resume={"approved": True}), cfg)
        final = await graph.aget_state(cfg)
        assert final.next == ()
        assert final.values["status"] == "done"
    finally:
        await pool.close()
