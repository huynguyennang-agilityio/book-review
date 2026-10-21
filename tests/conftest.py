"""Fixture chung. Test cần Postgres đọc `TEST_DATABASE_URL` (kết nối quản trị, vd
`postgresql://postgres:postgres@localhost:5432/postgres`); mỗi phiên test tạo một database
trống riêng, chạy migration, xong thì xoá."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from book_review_api.db import AppPool, make_app_pool
from book_review_api.migrate import migrate


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        if os.environ.get("REQUIRE_DB_TESTS"):
            pytest.fail("REQUIRE_DB_TESTS bật nhưng thiếu TEST_DATABASE_URL")
        pytest.skip("Cần TEST_DATABASE_URL để chạy test với Postgres")
    name = f"book_review_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    url = make_conninfo(admin_url, dbname=name)
    try:
        asyncio.run(migrate(url))
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture
async def app_pool(database_url: str) -> AsyncIterator[AppPool]:
    pool = make_app_pool(database_url)
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def make_user(database_url: str) -> Callable[[str], str]:
    """Thêm người dùng vào `auth.users`, trả về id (trên Supabase việc này do Supabase Auth làm)."""

    def create(email: str) -> str:
        user_id = str(uuid.uuid4())
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("insert into auth.users (id, email) values (%s, %s)", [user_id, email])
        return user_id

    return create
