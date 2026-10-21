"""Retriever trong bộ nhớ cho eval và script chạy thử: không cần Postgres.

Có `embeddings` thì xếp theo cosine; không có thì xếp theo số từ trùng với câu hỏi. Không thay
cho `retrieve.retrieve` (hybrid + RRF trên pgvector) ở môi trường thật.
"""

import math
from collections.abc import Sequence

from langchain_core.embeddings import Embeddings

from book_review_api.rag.ingest import Document
from book_review_api.rag.retrieve import _WORD_RE, Chunk


def to_chunks(docs: Sequence[Document]) -> list[Chunk]:
    """Chunk có id ổn định theo `source_id` và `chunk_index`."""
    return [
        Chunk(
            id=f"{d.metadata.get('source_id')}:{d.metadata.get('chunk_index', i)}",
            content=d.page_content,
            metadata=dict(d.metadata),
        )
        for i, d in enumerate(docs)
    ]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class InMemoryRetriever:
    def __init__(
        self, chunks: Sequence[Chunk], embeddings: Embeddings | None = None, top_n: int = 4
    ) -> None:
        self.chunks = list(chunks)
        self.embeddings = embeddings
        self.top_n = top_n
        self._vectors = (
            embeddings.embed_documents([c.content for c in chunks]) if embeddings else []
        )

    def __call__(self, query: str) -> list[Chunk]:
        if self.embeddings is not None:
            q = self.embeddings.embed_query(query)
            scores = [_cosine(q, v) for v in self._vectors]
        else:
            words = {w.lower() for w in _WORD_RE.findall(query)}
            scores = [
                float(len(words & {w.lower() for w in _WORD_RE.findall(c.content)}))
                for c in self.chunks
            ]
        order = sorted(range(len(self.chunks)), key=lambda i: -scores[i])[: self.top_n]
        return [self.chunks[i] for i in order if scores[i] > 0]
