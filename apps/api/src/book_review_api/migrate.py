"""Chạy migration SQL trong `db/migrations` rồi tạo bảng của LangGraph.

uv run python -m book_review_api.migrate [--database-url URL]
"""

import argparse
import asyncio
from pathlib import Path

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from book_review_api.config import get_settings
from book_review_api.db import LANGGRAPH_SCHEMA

# apps/api/src/book_review_api/migrate.py -> thư mục gốc repo
MIGRATIONS_DIR = Path(__file__).resolve().parents[4] / "db" / "migrations"

# Khoá để hai tiến trình migrate cùng lúc không chạy chồng nhau.
_LOCK_ID = 4_242_001


async def apply_sql_migrations(
    database_url: str, migrations_dir: Path = MIGRATIONS_DIR
) -> list[str]:
    """Chạy các file `*.sql` chưa chạy, theo thứ tự tên. Trả về danh sách file vừa chạy."""
    applied: list[str] = []
    async with await AsyncConnection.connect(database_url, autocommit=True) as conn:
        await conn.execute("select pg_advisory_lock(%s)", [_LOCK_ID])
        try:
            await conn.execute("create schema if not exists app_private")
            await conn.execute("revoke all on schema app_private from public")
            await conn.execute(
                "create table if not exists app_private.schema_migrations ("
                " version text primary key,"
                " applied_at timestamptz not null default now())"
            )
            cur = await conn.execute("select version from app_private.schema_migrations")
            done = {row[0] for row in await cur.fetchall()}
            for path in sorted(migrations_dir.glob("*.sql")):
                if path.name in done:
                    continue
                async with conn.transaction():
                    await conn.execute(path.read_text(encoding="utf-8"))
                    await conn.execute(
                        "insert into app_private.schema_migrations (version) values (%s)",
                        [path.name],
                    )
                applied.append(path.name)
        finally:
            await conn.execute("select pg_advisory_unlock(%s)", [_LOCK_ID])
    return applied


async def setup_langgraph(database_url: str) -> None:
    """Tạo bảng checkpoint và store trong schema `langgraph` (idempotent)."""
    # Import muộn để `--help` không phải nạp LangGraph.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore

    async with await AsyncConnection.connect(
        database_url,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
        options=f"-c search_path={LANGGRAPH_SCHEMA}",
    ) as conn:
        await AsyncPostgresSaver(conn).setup()
        await AsyncPostgresStore(conn).setup()


async def migrate(database_url: str) -> list[str]:
    applied = await apply_sql_migrations(database_url)
    await setup_langgraph(database_url)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None, help="mặc định lấy DATABASE_URL")
    args = parser.parse_args()
    applied = asyncio.run(migrate(args.database_url or get_settings().database_url))
    print("Đã chạy: " + ", ".join(applied) if applied else "Không có migration mới.")


if __name__ == "__main__":
    main()
