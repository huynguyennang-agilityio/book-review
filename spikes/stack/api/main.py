"""FastAPI expose graph hello ở /agent qua AG-UI."""

import os
from contextlib import asynccontextmanager

from agui_adapter import mount_agent
from dotenv import load_dotenv
from fastapi import FastAPI
from graph import build_graph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/book_review"
)

# autocommit + prepare_threshold=0 là yêu cầu của PostgresSaver khi dùng pool.
pool = AsyncConnectionPool(
    DATABASE_URL,
    open=False,
    kwargs={"autocommit": True, "prepare_threshold": 0},
)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # AsyncPostgresSaver cần event loop đang chạy nên phải tạo trong lifespan,
    # kéo theo việc gắn route /agent ở đây thay vì lúc import.
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
    await checkpointer.setup()
    mount_agent(app, build_graph(checkpointer), name="hello", path="/agent")
    yield
    await pool.close()


app = FastAPI(title="Spike stack ngày 2", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
