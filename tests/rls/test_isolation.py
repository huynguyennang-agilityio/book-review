"""RLS: user B không đọc, sửa, xoá được dữ liệu của user A, kể cả khi đoán đúng id."""

from collections.abc import Callable
from typing import Any

import psycopg
import pytest

from book_review_api.auth import CurrentUser
from book_review_api.db import AppPool, user_transaction

pytestmark = pytest.mark.anyio


@pytest.fixture
def users(make_user: Callable[[str], str]) -> tuple[CurrentUser, CurrentUser]:
    a = CurrentUser(user_id=make_user("a@example.com"))
    b = CurrentUser(user_id=make_user("b@example.com"))
    return a, b


async def fetch_all(pool: AppPool, user: CurrentUser, sql: str, params: Any = None) -> list[Any]:
    async with user_transaction(pool, user) as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchall()


async def rowcount(pool: AppPool, user: CurrentUser, sql: str, params: Any = None) -> int:
    async with user_transaction(pool, user) as conn:
        cur = await conn.execute(sql, params)
        return cur.rowcount


async def seed(pool: AppPool, owner: CurrentUser) -> dict[str, Any]:
    """Tạo 1 project, 1 asset, 1 document, 1 chunk cho `owner`."""
    async with user_transaction(pool, owner) as conn:
        project = await (
            await conn.execute(
                "insert into projects (book_title, thread_id)"
                " values ('Nhà giả kim', gen_random_uuid()::text) returning id, user_id"
            )
        ).fetchone()
        assert project is not None
        asset = await (
            await conn.execute(
                "insert into assets (project_id, kind, storage_path)"
                " values (%s, 'image', 'a/1.png') returning id",
                [project["id"]],
            )
        ).fetchone()
        document = await (
            await conn.execute(
                "insert into documents (project_id, content_hash) values (%s, 'h1') returning id",
                [project["id"]],
            )
        ).fetchone()
        assert asset is not None and document is not None
        chunk = await (
            await conn.execute(
                "insert into chunks (document_id, chunk_index, content)"
                " values (%s, 0, 'nội dung riêng') returning id",
                [document["id"]],
            )
        ).fetchone()
        assert chunk is not None
    return {
        "user_id": str(project["user_id"]),
        "projects": project["id"],
        "assets": asset["id"],
        "documents": document["id"],
        "chunks": chunk["id"],
    }


TABLES = ["projects", "assets", "documents", "chunks"]


async def test_owner_reads_own_rows(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser]
) -> None:
    a, _ = users
    ids = await seed(app_pool, a)
    # `user_id` lấy từ auth.uid(), không do client gửi.
    assert ids["user_id"] == a.user_id
    for table in TABLES:
        rows = await fetch_all(app_pool, a, f"select id from {table} where id = %s", [ids[table]])
        assert len(rows) == 1, table


@pytest.mark.parametrize("table", TABLES)
async def test_other_user_cannot_read_update_delete(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser], table: str
) -> None:
    a, b = users
    ids = await seed(app_pool, a)
    row_id = ids[table]

    assert await fetch_all(app_pool, b, f"select * from {table}") == []
    assert await fetch_all(app_pool, b, f"select * from {table} where id = %s", [row_id]) == []
    assert (
        await rowcount(app_pool, b, f"update {table} set user_id = user_id where id = %s", [row_id])
        == 0
    )
    assert await rowcount(app_pool, b, f"delete from {table} where id = %s", [row_id]) == 0
    # A vẫn còn nguyên dữ liệu.
    assert len(await fetch_all(app_pool, a, f"select id from {table} where id = %s", [row_id])) == 1


async def test_cannot_insert_for_another_user(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser]
) -> None:
    a, b = users
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await rowcount(
            app_pool,
            b,
            "insert into projects (user_id, book_title, thread_id) values (%s, 'x', 'x-thread')",
            [a.user_id],
        )


async def test_cannot_move_own_row_to_another_user(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser]
) -> None:
    a, b = users
    ids = await seed(app_pool, b)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await rowcount(
            app_pool,
            b,
            "update projects set user_id = %s where id = %s",
            [a.user_id, ids["projects"]],
        )


async def test_cannot_attach_to_another_users_project(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser]
) -> None:
    a, b = users
    ids = await seed(app_pool, a)
    # Khoá ngoại (project_id, user_id): asset của B không gắn được vào project của A.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        await rowcount(
            app_pool,
            b,
            "insert into assets (project_id, kind, storage_path) values (%s, 'image', 'x.png')",
            [ids["projects"]],
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        await rowcount(
            app_pool,
            b,
            "insert into chunks (document_id, chunk_index, content) values (%s, 1, 'x')",
            [ids["documents"]],
        )


async def test_anonymous_role_sees_nothing(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser]
) -> None:
    a, _ = users
    await seed(app_pool, a)
    async with app_pool.connection() as conn, conn.transaction():
        await conn.execute("set local role anon")
        for table in TABLES:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(f"select * from {table}")


async def test_authenticated_without_claims_sees_nothing(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser]
) -> None:
    a, _ = users
    await seed(app_pool, a)
    async with app_pool.connection() as conn, conn.transaction():
        await conn.execute("set local role authenticated")
        for table in TABLES:
            cur = await conn.execute(f"select * from {table}")
            assert await cur.fetchall() == [], table


async def test_claims_do_not_leak_to_next_transaction(
    app_pool: AppPool, users: tuple[CurrentUser, CurrentUser]
) -> None:
    a, _ = users
    await seed(app_pool, a)
    async with app_pool.connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "select set_config('role', 'authenticated', true),"
                " set_config('request.jwt.claims', %s, true)",
                [f'{{"sub": "{a.user_id}"}}'],
            )
        cur = await conn.execute("select current_user as role, auth.uid() as uid")
        row = await cur.fetchone()
        assert row is not None
        assert row["role"] != "authenticated"
        assert row["uid"] is None
