"""Hybrid retrieval (vector + full-text, gộp bằng RRF) rồi rerank.

`retrieve(book_id, query)` luôn lọc theo `book_id`; chạy trên engine nào thì RLS của engine đó
quyết định thấy chunk riêng của ai (xem `index.make_vector_engine`).
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from sqlalchemy import Engine, text

from book_review_api.config import Settings, get_settings
from book_review_api.rag.index import COLLECTION_NAME

# Hằng số làm mượt của Reciprocal Rank Fusion (giá trị chuẩn trong bài báo gốc).
RRF_K = 60
# Mỗi nhánh lấy nhiều hơn top-k để phần gộp có chỗ chọn.
CANDIDATE_FACTOR = 3

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Chunk:
    """Một chunk tìm được. `id` là `langchain_pg_embedding.id` (citation ngày 8 trỏ vào đây)."""

    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class Reranker(Protocol):
    def rerank(self, query: str, chunks: Sequence[Chunk], top_n: int) -> list[Chunk]: ...


def fulltext_query(query: str) -> str | None:
    """Chuỗi `to_tsquery` kiểu OR từ các từ của câu hỏi (không có từ nào thì `None`).

    Chỉ giữ ký tự chữ/số nên không thể chèn toán tử tsquery từ câu hỏi của người dùng.
    """
    words = dict.fromkeys(w.lower() for w in _WORD_RE.findall(query))
    return " | ".join(words) if words else None


def rrf_merge(rankings: Sequence[Sequence[Chunk]], k: int = RRF_K) -> list[Chunk]:
    """Reciprocal Rank Fusion: điểm = tổng 1/(k + hạng) qua các danh sách; hòa thì giữ thứ tự
    xuất hiện đầu tiên."""
    scores: dict[str, float] = {}
    first: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            first.setdefault(chunk.id, chunk)
    order = sorted(scores, key=lambda cid: -scores[cid])  # sort ổn định
    return [replace(first[cid], score=scores[cid]) for cid in order]


_VECTOR_SQL = text(
    """
    select e.id, e.document, e.cmetadata
    from public.langchain_pg_embedding e
    join public.langchain_pg_collection c on c.uuid = e.collection_id
    where c.name = :collection and e.book_id = :book_id
    order by e.embedding <=> cast(:embedding as vector)
    limit :limit
    """
)

_FULLTEXT_SQL = text(
    """
    select e.id, e.document, e.cmetadata
    from public.langchain_pg_embedding e
    join public.langchain_pg_collection c on c.uuid = e.collection_id,
         to_tsquery('simple', :tsquery) q
    where c.name = :collection and e.book_id = :book_id and e.fts @@ q
    order by ts_rank_cd(e.fts, q) desc, e.id
    limit :limit
    """
)


def _rows_to_chunks(rows: Sequence[Any]) -> list[Chunk]:
    return [Chunk(id=r[0], content=r[1] or "", metadata=dict(r[2] or {})) for r in rows]


def vector_search(
    engine: Engine, embeddings: Embeddings, book_id: str, query: str, limit: int
) -> list[Chunk]:
    vec = embeddings.embed_query(query)
    literal = "[" + ",".join(repr(float(x)) for x in vec) + "]"
    with engine.begin() as conn:
        rows = conn.execute(
            _VECTOR_SQL,
            {
                "collection": COLLECTION_NAME,
                "book_id": book_id,
                "embedding": literal,
                "limit": limit,
            },
        ).fetchall()
    return _rows_to_chunks(rows)


def fulltext_search(engine: Engine, book_id: str, query: str, limit: int) -> list[Chunk]:
    tsquery = fulltext_query(query)
    if tsquery is None:
        return []
    with engine.begin() as conn:
        rows = conn.execute(
            _FULLTEXT_SQL,
            {"collection": COLLECTION_NAME, "book_id": book_id, "tsquery": tsquery, "limit": limit},
        ).fetchall()
    return _rows_to_chunks(rows)


class LLMReranker:
    """Nhờ chat model xếp lại các chunk theo độ liên quan; lỗi hoặc đầu ra hỏng thì giữ nguyên
    thứ tự đầu vào (rerank chỉ làm tốt hơn, không được làm hỏng truy xuất)."""

    def __init__(self, model: BaseChatModel, max_chars: int = 1200) -> None:
        self.model = model
        self.max_chars = max_chars

    def _prompt(self, query: str, chunks: Sequence[Chunk]) -> str:
        passages = "\n\n".join(f"[{i}] {c.content[: self.max_chars]}" for i, c in enumerate(chunks))
        return (
            "Bạn xếp hạng các đoạn văn theo mức độ giúp trả lời câu hỏi.\n"
            f"Câu hỏi: {query}\n\nCác đoạn:\n{passages}\n\n"
            "Chỉ trả về một mảng JSON các chỉ số đoạn, từ liên quan nhất đến kém nhất, "
            "ví dụ [2, 0, 1]. Không giải thích."
        )

    def rerank(self, query: str, chunks: Sequence[Chunk], top_n: int) -> list[Chunk]:
        if len(chunks) <= 1:
            return list(chunks)[:top_n]
        try:
            reply = self.model.invoke(self._prompt(query, chunks))
            raw = reply.content if isinstance(reply.content, str) else json.dumps(reply.content)
            match = re.search(r"\[[-\d\s,]*\]", raw)
            picked = json.loads(match.group(0)) if match else []
        except Exception:  # noqa: BLE001 - mọi lỗi của LLM đều rơi về thứ tự RRF
            return list(chunks)[:top_n]
        order: list[int] = []
        for i in picked:
            if isinstance(i, int) and 0 <= i < len(chunks) and i not in order:
                order.append(i)
        order += [i for i in range(len(chunks)) if i not in order]
        return [chunks[i] for i in order[:top_n]]


def make_reranker(settings: Settings | None = None) -> Reranker | None:
    """Reranker theo config: `none` -> `None` (giữ thứ tự RRF), `llm` -> Gemini."""
    settings = settings or get_settings()
    provider = settings.rerank_provider.lower()
    if provider == "none":
        return None
    if provider == "llm":
        from book_review_api.providers.llm_gemini import make_chat_model

        return LLMReranker(make_chat_model(settings))
    raise ValueError(f"rerank_provider không hợp lệ: {settings.rerank_provider!r}")


def retrieve(
    book_id: str,
    query: str,
    *,
    engine: Engine,
    embeddings: Embeddings,
    reranker: Reranker | None = None,
    settings: Settings | None = None,
) -> list[Chunk]:
    """Top `rerank_top_n` chunk của sách `book_id` cho câu hỏi `query`.

    Lấy `retrieve_top_k` ứng viên từ vector + full-text (gộp RRF), rồi rerank (nếu có) xuống
    `rerank_top_n`. `engine` quyết định phạm vi RLS (chunk công khai + chunk của user).
    """
    if not book_id:
        raise ValueError("book_id là bắt buộc")
    if not query.strip():
        return []
    settings = settings or get_settings()
    k, n = settings.retrieve_top_k, settings.rerank_top_n
    limit = k * CANDIDATE_FACTOR
    merged = rrf_merge(
        [
            vector_search(engine, embeddings, book_id, query, limit),
            fulltext_search(engine, book_id, query, limit),
        ]
    )[:k]
    if reranker is None:
        return merged[:n]
    return reranker.rerank(query, merged, n)
