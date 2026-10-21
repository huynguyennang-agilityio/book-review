"""Nạp chunk vào pgvector bằng Indexing API của LangChain (chế độ `incremental`).

Mỗi chunk có key = băm(phạm vi, source_id, chunk_index, content_hash). Nạp lại cùng nguồn thì
mọi key đã có nên không embed lại và không tạo dòng mới; nội dung đổi thì chunk có key mới được
thêm và chunk cũ của nguồn đó bị xoá.
"""

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from langchain_classic.indexes import SQLRecordManager
from langchain_core.documents import Document as LCDocument
from langchain_core.embeddings import Embeddings
from langchain_core.indexing import IndexingResult, index
from langchain_postgres import PGVector
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import URL, Engine, create_engine, event

from book_review_api.rag.ingest import Document, IngestError, SnapshotStore, ingest_source

COLLECTION_NAME = "book_chunks"
RECORD_SCHEMA = "app_private"
_URL_PARTS = {"user", "password", "host", "port", "dbname"}


def sqlalchemy_url(database_url: str) -> URL:
    """Chuỗi kết nối libpq (URI hoặc `key=value`) -> URL SQLAlchemy dùng driver psycopg 3."""
    p = {k: str(v) for k, v in conninfo_to_dict(database_url).items() if v is not None}
    port = p.get("port")
    return URL.create(
        "postgresql+psycopg",
        username=p.get("user"),
        password=p.get("password"),
        host=p.get("host"),
        port=int(port) if port else None,
        database=p.get("dbname"),
        query={k: v for k, v in p.items() if k not in _URL_PARTS},
    )


def make_vector_engine(database_url: str, user_id: str | None = None) -> Engine:
    """Engine cho PGVector. Có `user_id` thì mỗi transaction chạy dưới role `authenticated` với
    claims của người đó (như `db.user_transaction`) nên RLS quyết định thấy/ghi dòng nào; không
    có thì chạy bằng quyền kết nối (nạp chunk công khai)."""
    engine = create_engine(sqlalchemy_url(database_url))
    if user_id is not None:
        claims = json.dumps({"sub": user_id, "role": "authenticated"})

        @event.listens_for(engine, "begin")
        def _scope_to_user(conn: Any) -> None:
            conn.exec_driver_sql(
                "select set_config('role', 'authenticated', true),"
                " set_config('request.jwt.claims', %s, true)",
                (claims,),
            )

    return engine


def make_record_engine(database_url: str) -> Engine:
    """Engine cho `SQLRecordManager`: bảng nằm ở `app_private`, chỉ chứa hash nên không qua RLS."""
    return create_engine(
        sqlalchemy_url(database_url),
        connect_args={"options": f"-c search_path={RECORD_SCHEMA}"},
    )


def make_vector_store(embeddings: Embeddings, engine: Engine) -> PGVector:
    # Bảng và extension do migration tạo, người dùng thường không có quyền DDL.
    return PGVector(
        embeddings=embeddings,
        connection=engine,
        collection_name=COLLECTION_NAME,
        create_extension=False,
        use_jsonb=True,
    )


def scope_of(user_id: str | None) -> str:
    return f"user:{user_id}" if user_id else "public"


def make_record_manager(engine: Engine, user_id: str | None = None) -> SQLRecordManager:
    return SQLRecordManager(f"{COLLECTION_NAME}/{scope_of(user_id)}", engine=engine)


def chunk_key(doc: LCDocument) -> str:
    """Key ổn định của chunk. Không dùng toàn bộ metadata vì `ingested_at` đổi mỗi lần nạp."""
    m = doc.metadata
    raw = "|".join(
        str(m.get(k)) for k in ("user_id", "book_id", "source_id", "chunk_index", "content_hash")
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def to_langchain(doc: Document) -> LCDocument:
    return LCDocument(page_content=doc.page_content, metadata=dict(doc.metadata))


def index_chunks(
    docs: Sequence[Document],
    *,
    vector_store: PGVector,
    record_manager: SQLRecordManager,
) -> IndexingResult:
    """Nạp chunk của một hoặc nhiều nguồn. Mọi chunk phải cùng phạm vi (user hoặc công khai)."""
    if not docs:
        return {"num_added": 0, "num_updated": 0, "num_skipped": 0, "num_deleted": 0}
    # Cleanup `incremental` chạy sau từng batch; batch nhỏ hơn số chunk của nguồn sẽ xoá nhầm
    # chunk chưa kịp được ghi nhận lại, nên gom cả lần nạp vào một batch.
    return index(
        [to_langchain(d) for d in docs],
        record_manager,
        vector_store,
        cleanup="incremental",
        source_id_key="source_id",
        batch_size=len(docs),
        key_encoder=chunk_key,
    )


def index_source(
    source: Any,
    *,
    vector_store: PGVector,
    record_manager: SQLRecordManager,
    snapshot_store: SnapshotStore | None = None,
    **ingest_kwargs: Any,
) -> IndexingResult:
    """Ingest (clean + chunk + snapshot) rồi nạp vào pgvector."""
    docs = ingest_source(source, snapshot_store=snapshot_store, **ingest_kwargs)
    if not docs:
        raise IngestError("Nguồn không tạo được chunk nào")
    return index_chunks(docs, vector_store=vector_store, record_manager=record_manager)
