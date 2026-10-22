"""So sánh cấu hình retrieval trên dataset golden: chunk, overlap, top-k, top-n, rerank.

    uv run python evals/run_retrieval.py                  # embeddings Gemini thật, có cache
    uv run python evals/run_retrieval.py --rerank         # thêm cấu hình rerank bằng LLM
    uv run python evals/run_retrieval.py --langsmith      # đẩy mỗi cấu hình thành một experiment

Mỗi dữ kiện trong `facts.json` là một truy vấn; chunk "liên quan" là chunk chứa `needle`.
Chỉ số (trung bình trên mọi truy vấn):
- recall: truy vấn có ít nhất một chunk liên quan trong top-n.
- precision: tỉ lệ chunk liên quan trong top-n.
- MRR: nghịch đảo hạng của chunk liên quan đầu tiên.
- ctx_tokens: số token ước tính của ngữ cảnh đưa vào storyboard.

Chế độ `book` lọc theo sách như production (`retrieve` luôn lọc `book_id`); chế độ `pool` gộp cả
20 sách vào một kho, không lọc, truy vấn có kèm tên sách. Nhánh full-text mô phỏng bằng đếm từ trùng
(không cần Postgres), nhánh vector dùng embeddings Gemini; gộp bằng `rrf_merge` như production.
Báo cáo ghi ra `docs/evals/retrieval_comparison.md` và `.json`.
"""

import argparse
import hashlib
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from book_review_api.config import get_settings
from book_review_api.providers.llm_gemini import make_chat_model, make_embeddings
from book_review_api.rag.golden import GoldenBook, load_golden
from book_review_api.rag.ingest import (
    _split_sections,
    chunk_section,
    estimate_tokens,
    normalize_text,
)
from book_review_api.rag.retrieve import _WORD_RE, CANDIDATE_FACTOR, Chunk, LLMReranker, rrf_merge
from book_review_api.storyboard.validate import fold_quote

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden"
OUT = ROOT / "evals" / "out" / "retrieval"
REPORT_MD = ROOT / "docs" / "evals" / "retrieval_comparison.md"
REPORT_JSON = ROOT / "docs" / "evals" / "retrieval_comparison.json"


@dataclass(frozen=True)
class Config:
    name: str
    max_tokens: int
    overlap_pct: int  # overlap theo % của max_tokens
    mode: str = "hybrid"  # vector | keyword | hybrid
    top_k: int = 8  # số chunk giữ sau khi gộp, trước rerank
    top_n: int = 4  # số chunk cuối cùng
    rerank: bool = False


# --- Cache trên đĩa -----------------------------------------------------------------


class DiskCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = (
            json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        )

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def put_many(self, items: dict[str, Any]) -> None:
        self.data.update(items)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:20]


class CachedEmbedder:
    """Embeddings Gemini có cache theo nội dung; tài liệu và câu hỏi tách khóa (task type khác)."""

    def __init__(self, embeddings: Any, cache: DiskCache) -> None:
        self.embeddings, self.cache = embeddings, cache

    def _retry(self, fn: Any, arg: Any) -> Any:
        for attempt in range(8):
            try:
                return fn(arg)
            except Exception as e:  # noqa: BLE001 - 429 của gói free: chờ rồi thử lại
                if "RESOURCE_EXHAUSTED" not in str(e) or attempt == 7:
                    raise
                time.sleep(35)

    def _fill(self, texts: Sequence[str], prefix: str, embed: Any) -> list[list[float]]:
        missing = list(dict.fromkeys(t for t in texts if self.cache.get(prefix + _h(t)) is None))
        for i in range(0, len(missing), 50):
            batch = missing[i : i + 50]
            self.cache.put_many(
                dict(zip((prefix + _h(t) for t in batch), self._retry(embed, batch), strict=True))
            )
        return [self.cache.get(prefix + _h(t)) for t in texts]

    def docs(self, texts: Sequence[str]) -> list[list[float]]:
        return self._fill(texts, "d:", self.embeddings.embed_documents)

    def queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._fill(
            texts, "q:", lambda b: [self._retry(self.embeddings.embed_query, t) for t in b]
        )


# --- Chunk theo cấu hình ------------------------------------------------------------


def build_chunks(book: GoldenBook, cfg: Config) -> list[Chunk]:
    chunks: list[Chunk] = []
    for name, text in book.sources.items():
        sid = f"{book.slug}/{name}"
        pieces = [
            c
            for _, body in _split_sections(normalize_text(text))
            for c in chunk_section(
                body,
                max_tokens=cfg.max_tokens,
                min_tokens=cfg.max_tokens // 2,
                overlap_tokens=cfg.max_tokens * cfg.overlap_pct // 100,
            )
        ]
        chunks += [
            Chunk(id=f"{sid}:{i}", content=c, metadata={"book_id": book.slug})
            for i, c in enumerate(pieces)
        ]
    return chunks


# --- Truy xuất trong bộ nhớ ---------------------------------------------------------


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


class Index:
    def __init__(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        self.chunks, self.vectors = list(chunks), list(vectors)
        self.words = [_words(c.content) for c in self.chunks]

    def search(
        self, query: str, qvec: Sequence[float], cfg: Config, book_id: str | None
    ) -> list[Chunk]:
        pool = [
            i
            for i, c in enumerate(self.chunks)
            if book_id is None or c.metadata["book_id"] == book_id
        ]
        cand = cfg.top_k * CANDIDATE_FACTOR
        vec = sorted(pool, key=lambda i: -_cosine(qvec, self.vectors[i]))[:cand]
        qw = _words(query)
        kw_scores = {i: len(qw & self.words[i]) for i in pool}
        kw = sorted((i for i in pool if kw_scores[i] > 0), key=lambda i: -kw_scores[i])[:cand]
        if cfg.mode == "vector":
            ranked = [self.chunks[i] for i in vec]
        elif cfg.mode == "keyword":
            ranked = [self.chunks[i] for i in kw]
        else:
            ranked = rrf_merge([[self.chunks[i] for i in vec], [self.chunks[i] for i in kw]])
        return ranked[: cfg.top_k]


# --- Đo -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    slug: str
    title: str
    fact_id: str
    text: str
    needle: str


def queries_for(books: Sequence[GoldenBook]) -> list[Query]:
    return [
        Query(b.slug, b.title, f.id, f.fact, fold_quote(f.needle)) for b in books for f in b.facts
    ]


def score(hits: Sequence[Chunk], needle: str) -> dict[str, float]:
    rel = [fold_quote(c.content).find(needle) >= 0 for c in hits]
    first = next((i for i, r in enumerate(rel) if r), None)
    return {
        "recall": 1.0 if any(rel) else 0.0,
        "precision": sum(rel) / len(rel) if rel else 0.0,
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
        "ctx_tokens": float(sum(estimate_tokens(c.content) for c in hits)),
    }


def evaluate(
    cfg: Config,
    books: Sequence[GoldenBook],
    scope: str,
    embedder: CachedEmbedder,
    reranker: LLMReranker | None,
    rerank_cache: DiskCache,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    all_chunks = {b.slug: build_chunks(b, cfg) for b in books}
    flat = [c for b in books for c in all_chunks[b.slug]]
    index = Index(flat, embedder.docs([c.content for c in flat]))
    qs = queries_for(books)
    texts = [q.text if scope == "book" else f"{q.title}: {q.text}" for q in qs]
    qvecs = embedder.queries(texts)

    rows: list[dict[str, Any]] = []
    for q, text, qvec in zip(qs, texts, qvecs, strict=True):
        hits = index.search(text, qvec, cfg, q.slug if scope == "book" else None)
        if cfg.rerank and reranker is not None:
            key = "r:" + _h(text + "|" + "|".join(c.id for c in hits) + f"|{cfg.top_n}")
            cached = rerank_cache.get(key)
            if cached is None:
                cached = [c.id for c in reranker.rerank(text, hits, cfg.top_n)]
                rerank_cache.put_many({key: cached})
            by_id = {c.id: c for c in hits}
            hits = [by_id[i] for i in cached if i in by_id]
        else:
            hits = hits[: cfg.top_n]
        rows.append(
            {
                "book": q.slug,
                "fact": q.fact_id,
                "hits": [c.id for c in hits],
                **score(hits, q.needle),
            }
        )
    avg = {
        k: round(sum(r[k] for r in rows) / len(rows), 4)
        for k in ("recall", "precision", "mrr", "ctx_tokens")
    }
    avg["chunks"] = float(len(flat))
    return avg, rows


# --- Cấu hình thử -------------------------------------------------------------------


def grid(with_rerank: bool) -> list[Config]:
    cfgs: list[Config] = []
    # 1) chunk x overlap, hybrid, top_k 8 -> top_n 4 (mặc định hiện tại cho top-k)
    for size in (60, 100, 150, 250, 800):
        for ov in (0, 15):
            cfgs.append(Config(f"chunk{size}-ov{ov}", size, ov))
    # 2) chế độ truy xuất, ở chunk 100 và 800
    for size in (100, 800):
        for mode in ("vector", "keyword"):
            cfgs.append(Config(f"chunk{size}-ov15-{mode}", size, 15, mode=mode))
    # 3) top-k / top-n ở chunk 100
    for k, n in ((4, 2), (8, 2), (8, 3), (8, 6), (12, 4), (12, 6)):
        cfgs.append(Config(f"chunk100-ov15-k{k}-n{n}", 100, 15, top_k=k, top_n=n))
    if with_rerank:
        for n in (2, 4):
            cfgs.append(Config(f"chunk100-ov15-k8-n{n}-rerank", 100, 15, top_n=n, rerank=True))
    return cfgs


def to_markdown(results: list[dict[str, Any]], scope: str) -> str:
    head = (
        "Cấu hình", "Chunk (token)", "Overlap", "Chế độ", "top-k", "top-n", "Rerank",
        "Số chunk", "Recall", "Precision", "MRR", "Token ngữ cảnh",
    )  # fmt: skip
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    for r in results:
        c, m = r["config"], r[scope]
        lines.append(
            f"| `{c['name']}` | {c['max_tokens']} | {c['overlap_pct']}% | {c['mode']} | "
            f"{c['top_k']} | {c['top_n']} | {'llm' if c['rerank'] else 'không'} | "
            f"{int(m['chunks'])} | "
            f"{m['recall']:.3f} | {m['precision']:.3f} | {m['mrr']:.3f} | {m['ctx_tokens']:.0f} |"
        )
    return "\n".join(lines)


def push_langsmith(cfg: Config, books: Sequence[GoldenBook], rows: list[dict[str, Any]]) -> None:
    from langsmith import Client

    client = Client()
    name = "book-review-golden-retrieval"
    qs = queries_for(books)
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(name, description="Truy vấn dữ kiện của 20 sách golden")
        client.create_examples(
            dataset_id=dataset.id,
            inputs=[{"book": q.slug, "fact": q.fact_id, "query": q.text} for q in qs],
            outputs=[{"needle": q.needle} for q in qs],
        )
    by_key = {(r["book"], r["fact"]): r for r in rows}

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"hits": by_key[(inputs["book"], inputs["fact"])]["hits"]}

    def metric(key: str) -> Any:
        def ev(run: Any, example: Any) -> dict[str, Any]:
            r = by_key[(example.inputs["book"], example.inputs["fact"])]
            return {"key": key, "score": r[key]}

        ev.__name__ = key
        return ev

    client.evaluate(
        target,
        data=name,
        evaluators=[metric("recall"), metric("precision"), metric("mrr")],
        experiment_prefix=cfg.name,
        metadata={**cfg.__dict__},
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerank", action="store_true", help="thêm cấu hình rerank bằng LLM")
    ap.add_argument("--langsmith", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    books = load_golden(GOLDEN)
    embedder = CachedEmbedder(make_embeddings(settings), DiskCache(OUT / "embeddings.json"))
    rerank_cache = DiskCache(OUT / "rerank.json")
    reranker = LLMReranker(make_chat_model(settings)) if args.rerank else None

    results: list[dict[str, Any]] = []
    for cfg in grid(args.rerank):
        book_m, rows = evaluate(cfg, books, "book", embedder, reranker, rerank_cache)
        pool_m, _ = evaluate(cfg, books, "pool", embedder, reranker, rerank_cache)
        print(
            f"{cfg.name:32} book R={book_m['recall']:.3f} P={book_m['precision']:.3f} "
            f"MRR={book_m['mrr']:.3f} | pool R={pool_m['recall']:.3f} P={pool_m['precision']:.3f} "
            f"MRR={pool_m['mrr']:.3f}"
        )
        results.append({"config": cfg.__dict__, "book": book_m, "pool": pool_m})
        if args.langsmith:
            push_langsmith(cfg, books, rows)

    REPORT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    REPORT_MD.write_text(
        "## Lọc theo sách (như production)\n\n"
        + to_markdown(results, "book")
        + "\n\n## Kho chung 20 sách, không lọc\n\n"
        + to_markdown(results, "pool")
        + "\n",
        encoding="utf-8",
    )
    print(f"Đã ghi {REPORT_JSON} và {REPORT_MD}")


if __name__ == "__main__":
    main()
