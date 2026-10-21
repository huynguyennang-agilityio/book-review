"""FastAPI app: auth, AG-UI endpoint, REST (xem docs/plan/day-03.md, day-04.md)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from book_review_api import projects
from book_review_api.auth import CurrentUser, current_user
from book_review_api.config import get_settings
from book_review_api.db import make_app_pool, make_graph_pool
from book_review_api.errors import register_error_handlers
from book_review_api.graph.build import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Saver/store cần event loop đang chạy nên tạo ở đây (spike ngày 2, lỗi 1).
    # Bảng đã có sẵn từ `python -m book_review_api.migrate`, không gọi setup() ở đây.
    settings = get_settings()
    app_pool = make_app_pool(settings.database_url)
    graph_pool = make_graph_pool(settings.database_url)
    await app_pool.open()
    await graph_pool.open()
    try:
        app.state.app_pool = app_pool
        app.state.graph = build_graph(
            checkpointer=AsyncPostgresSaver(graph_pool),
            store=AsyncPostgresStore(graph_pool),
        )
        yield
    finally:
        await graph_pool.close()
        await app_pool.close()


app = FastAPI(title="Book Review API", lifespan=lifespan)
register_error_handlers(app)
app.include_router(projects.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    return user
