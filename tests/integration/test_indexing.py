"""Nạp vào pgvector: lặp lại không trùng, đổi nội dung thì thay chunk, RLS theo user_id."""

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.indexing import IndexingResult
from sqlalchemy import Engine

from book_review_api.config import Settings
from book_review_api.rag.index import (
    index_source,
    make_record_engine,
    make_record_manager,
    make_vector_engine,
    make_vector_store,
)

DIM = 768
EngineFactory = Callable[[str | None], tuple[Engine, Engine]]
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
URL = "https://example.vn/nha_gia_kim.html"


class FakeEmbeddings(Embeddings):
    """Vector giả xác định theo nội dung; đếm số chữ được embed để kiểm tra không embed lại."""

    def __init__(self) -> None:
        self.embedded = 0

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [(digest[i % len(digest)] + 1) / 256 for i in range(DIM)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded += len(texts)
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture
def engines(database_url: str) -> Iterator[EngineFactory]:
    made: list[Engine] = []

    def make(user_id: str | None) -> tuple[Engine, Engine]:
        vec, rec = make_vector_engine(database_url, user_id), make_record_engine(database_url)
        made.extend([vec, rec])
        return vec, rec

    yield make
    for e in made:
        e.dispose()


def count(database_url: str, where: str = "true") -> int:
    with psycopg.connect(database_url) as conn:
        row = conn.execute(f"select count(*) from langchain_pg_embedding where {where}").fetchone()
    assert row is not None
    return int(row[0])


def test_embedding_dim_matches_migration(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "select atttypmod from pg_attribute"
            " where attrelid = 'langchain_pg_embedding'::regclass and attname = 'embedding'"
        ).fetchone()
    assert row is not None and row[0] == Settings().embedding_dim == DIM


def test_hnsw_index_exists(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "select indexdef from pg_indexes where indexname = 'langchain_pg_embedding_hnsw_idx'"
        ).fetchone()
    assert row is not None and "USING hnsw" in row[0]


def _public_index(
    database_url: str, engines: EngineFactory, emb: FakeEmbeddings, html: bytes, book: str
) -> IndexingResult:
    vec, rec = engines(None)
    return index_source(
        URL,
        data=html,
        book_id=book,
        vector_store=make_vector_store(emb, vec),
        record_manager=make_record_manager(rec),
    )


def test_reindex_same_source_no_duplicates(database_url: str, engines: EngineFactory) -> None:
    html = (FIXTURES / "nha_gia_kim.html").read_bytes()
    emb = FakeEmbeddings()
    first = _public_index(database_url, engines, emb, html, "nha-gia-kim")
    n = count(database_url)
    assert first["num_added"] == n > 0
    embedded = emb.embedded

    second = _public_index(database_url, engines, emb, html, "nha-gia-kim")
    assert second["num_added"] == 0 and second["num_deleted"] == 0
    assert second["num_skipped"] == n
    assert count(database_url) == n
    assert emb.embedded == embedded  # không gọi embedding lần hai


def test_changed_source_replaces_old_chunks(database_url: str, engines: EngineFactory) -> None:
    html = (FIXTURES / "nha_gia_kim.html").read_bytes()
    emb = FakeEmbeddings()
    _public_index(database_url, engines, emb, html, "book-b")
    old_docs = _contents(database_url, "book-b")

    changed = html.replace(b"Santiago", "Santiago Đã Đổi".encode())
    assert changed != html
    result = _public_index(database_url, engines, emb, changed, "book-b")
    assert result["num_added"] >= 1 and result["num_deleted"] >= 1
    new_docs = _contents(database_url, "book-b")
    assert len(new_docs) == len(old_docs)
    assert new_docs != old_docs
    assert any("Đã Đổi" in d for d in new_docs)
    assert not any("Đã Đổi" in d for d in old_docs)


def _contents(database_url: str, book: str) -> list[str]:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "select document from langchain_pg_embedding where book_id = %s"
            " order by (cmetadata->>'chunk_index')::int",
            [book],
        ).fetchall()
    return [r[0] for r in rows]


def test_private_chunks_isolated_by_user(
    database_url: str,
    engines: EngineFactory,
    make_user: Callable[[str], str],
) -> None:
    a, b = make_user("a@example.com"), make_user("b@example.com")
    emb = FakeEmbeddings()
    txt = (FIXTURES / "nha_gia_kim.html").read_bytes()  # nội dung bất kỳ, đặt tên .txt
    for uid in (a, b):
        vec, rec = engines(uid)
        # Cùng tên file và nội dung ở hai user vẫn là hai tập chunk riêng.
        index_source(
            "ghi_chu.txt",
            data=txt,
            book_id="book-priv",
            user_id=uid,
            vector_store=make_vector_store(emb, vec),
            record_manager=make_record_manager(rec, uid),
        )
    total_a = count(database_url, f"user_id = '{a}'")
    assert total_a > 0 and count(database_url, f"user_id = '{b}'") == total_a

    # A chỉ thấy chunk của A (và chunk công khai, hiện chưa có).
    vec_a, _ = engines(a)
    store_a = make_vector_store(emb, vec_a)
    hits = store_a.similarity_search("Santiago", k=50)
    assert any(h.metadata.get("user_id") == a for h in hits)
    assert all(h.metadata.get("user_id") in (a, None) for h in hits)

    # A không xoá được chunk của B.
    with vec_a.begin() as conn:
        deleted = conn.exec_driver_sql(
            "delete from langchain_pg_embedding where user_id = %s", (b,)
        ).rowcount
    assert deleted == 0


def test_user_cannot_write_public_or_foreign_chunks(
    database_url: str,
    engines: EngineFactory,
    make_user: Callable[[str], str],
) -> None:
    a, b = make_user("c@example.com"), make_user("d@example.com")
    vec_a, _ = engines(a)
    store = make_vector_store(FakeEmbeddings(), vec_a)
    from langchain_core.documents import Document

    for owner in (None, b):
        with pytest.raises(Exception, match="row-level security"):
            store.add_documents(
                [Document(page_content="x", metadata={"user_id": owner, "book_id": "z"})],
                ids=[f"bad-{owner}"],
            )


def test_public_chunks_visible_to_users(
    database_url: str,
    engines: EngineFactory,
    make_user: Callable[[str], str],
) -> None:
    emb = FakeEmbeddings()
    _public_index(database_url, engines, emb, (FIXTURES / "de_men.html").read_bytes(), "de-men-pub")
    u = make_user("e@example.com")
    vec_u, _ = engines(u)
    hits = make_vector_store(emb, vec_u).similarity_search(
        "Dế Mèn", k=5, filter={"book_id": "de-men-pub"}
    )
    assert hits
