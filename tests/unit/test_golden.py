"""Dataset golden: đủ 10 sách, mỗi dữ kiện có căn cứ trong nguồn."""

from pathlib import Path

from book_review_api.rag.golden import load_golden
from book_review_api.storyboard.validate import fold_quote

ROOT = Path(__file__).resolve().parents[2] / "evals" / "golden"


def test_ten_books_five_fiction_five_non_fiction() -> None:
    books = load_golden(ROOT)
    assert len(books) == 10
    assert sum(b.kind == "fiction" for b in books) == 5
    assert sum(b.kind == "non_fiction" for b in books) == 5


def test_every_fact_has_support_in_sources() -> None:
    for book in load_golden(ROOT):
        assert len(book.facts) >= 3, book.slug
        corpus = fold_quote(" ".join(book.sources.values()))
        for f in book.facts:
            assert fold_quote(f.needle) in corpus, f"{book.slug}/{f.id}: {f.needle!r}"


def test_sources_become_chunks_with_stable_ids() -> None:
    book = load_golden(ROOT)[0]
    chunks = book.chunks()
    assert chunks
    assert len({c.id for c in chunks}) == len(chunks)
    assert all(c.metadata["source_id"].startswith(book.slug) for c in chunks)


def test_in_memory_retriever_ranks_by_word_overlap() -> None:
    from book_review_api.rag.memory import InMemoryRetriever

    book = next(b for b in load_golden(ROOT) if b.slug == "sapiens")
    hits = InMemoryRetriever(book.chunks(), top_n=1)("ba cuộc cách mạng Nhận thức Nông nghiệp")
    assert len(hits) == 1
    assert "Cách mạng Nhận thức" in hits[0].content
    assert InMemoryRetriever(book.chunks())("zzzz qqqq") == []
