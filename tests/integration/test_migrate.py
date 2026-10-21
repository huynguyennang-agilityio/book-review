"""Migration chạy được từ DB trống (fixture `database_url`) và chạy lại không đổi gì."""

import psycopg
import pytest

from book_review_api.migrate import MIGRATIONS_DIR, apply_sql_migrations

pytestmark = pytest.mark.anyio


async def test_rerun_is_noop(database_url: str) -> None:
    assert await apply_sql_migrations(database_url) == []


def test_all_files_recorded(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute("select version from app_private.schema_migrations").fetchall()
    assert sorted(r[0] for r in rows) == sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))


def test_rls_enabled_on_app_tables(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "select relname, relrowsecurity from pg_class c"
            " join pg_namespace n on n.oid = c.relnamespace"
            " where n.nspname = 'public' and c.relkind = 'r'"
        ).fetchall()
    assert rows, "không có bảng nào trong public"
    assert {name for name, rls in rows if not rls} == set()


def test_langgraph_tables_outside_public(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "select table_schema, table_name from information_schema.tables"
            " where table_name in ('checkpoints', 'checkpoint_writes', 'store')"
        ).fetchall()
    assert {schema for schema, _ in rows} == {"langgraph"}
    assert len(rows) == 3
