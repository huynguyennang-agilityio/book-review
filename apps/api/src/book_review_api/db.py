"""Kết nối Postgres.

Hai pool:
- `app_pool`: bảng ứng dụng. Mọi truy vấn dữ liệu người dùng chạy trong `user_transaction`,
  với role `authenticated` và claims JWT của người gửi request, nên RLS của Postgres quyết định
  người dùng thấy dòng nào (giống PostgREST của Supabase).
- `graph_pool`: checkpoint và store của LangGraph, `search_path` trỏ vào schema `langgraph`.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, Request
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from book_review_api.auth import CurrentUser, current_user

LANGGRAPH_SCHEMA = "langgraph"

AppPool = AsyncConnectionPool[AsyncConnection[DictRow]]


def make_app_pool(database_url: str) -> AppPool:
    return AsyncConnectionPool(
        database_url,
        open=False,
        connection_class=AsyncConnection[DictRow],
        kwargs={"row_factory": dict_row},
    )


def make_graph_pool(database_url: str) -> AppPool:
    # Tham số theo AsyncPostgresSaver.from_conn_string (xem spike ngày 2, lỗi 1).
    return AsyncConnectionPool(
        database_url,
        open=False,
        connection_class=AsyncConnection[DictRow],
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={LANGGRAPH_SCHEMA}",
        },
    )


@asynccontextmanager
async def user_transaction(
    pool: AppPool, user: CurrentUser
) -> AsyncIterator[AsyncConnection[DictRow]]:
    """Transaction chạy dưới quyền người dùng. Role và claims chỉ sống trong transaction này."""
    claims: dict[str, Any] = {"sub": user.user_id, "role": "authenticated"}
    if user.email:
        claims["email"] = user.email
    async with pool.connection() as conn, conn.transaction():
        await conn.execute(
            "select set_config('role', 'authenticated', true),"
            " set_config('request.jwt.claims', %s, true)",
            [json.dumps(claims)],
        )
        yield conn


async def user_db(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> AsyncIterator[AsyncConnection[DictRow]]:
    async with user_transaction(request.app.state.app_pool, user) as conn:
        yield conn


UserDB = Annotated[AsyncConnection[DictRow], Depends(user_db)]
