"""FastAPI app: auth, AG-UI endpoint, REST (xem docs/plan/day-03.md, day-04.md)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from book_review_api import agui, memory_api, projects
from book_review_api.auth import CurrentUser, current_user
from book_review_api.cancel import RedisCancelFlags
from book_review_api.config import get_settings
from book_review_api.db import make_app_pool, make_graph_pool
from book_review_api.errors import register_error_handlers
from book_review_api.graph.build import build_graph
from book_review_api.graph.live import build_live_graph, make_live_scene_rewriter
from book_review_api.observability import install_log_filter, setup_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Saver/store cần event loop đang chạy nên tạo ở đây (spike ngày 2, lỗi 1).
    # Bảng đã có sẵn từ `python -m book_review_api.migrate`, không gọi setup() ở đây.
    settings = get_settings()
    setup_tracing()
    install_log_filter()
    app_pool = make_app_pool(settings.database_url)
    graph_pool = make_graph_pool(settings.database_url)
    await app_pool.open()
    await graph_pool.open()
    try:
        app.state.app_pool = app_pool
        checkpointer = AsyncPostgresSaver(graph_pool)
        store = AsyncPostgresStore(graph_pool)
        app.state.store = store
        flags = RedisCancelFlags(settings.redis_url)
        app.state.cancel_flags = flags
        # Thiếu GOOGLE_API_KEY (CI, test) thì dùng graph khung với node rỗng.
        app.state.graph = (
            build_live_graph(settings, checkpointer, store, flags)
            if settings.google_api_key
            else build_graph(checkpointer=checkpointer, store=store, cancel_flags=flags)
        )
        app.state.scene_rewriter = (
            make_live_scene_rewriter(settings) if settings.google_api_key else None
        )
        app.state.agent = agui.make_agent(app.state.graph)
        yield
    finally:
        await graph_pool.close()
        await app_pool.close()


app = FastAPI(title="Book Review API", lifespan=lifespan)
register_error_handlers(app)
app.include_router(projects.router)
app.include_router(agui.router)
app.include_router(memory_api.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    return user
