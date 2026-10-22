"""Chạy thật node storyboard trên sách golden bằng Gemini, in kịch bản và kiểm tra citation.

    uv run python scripts/run_storyboard.py nha-gia-kim sapiens

Cần GOOGLE_API_KEY trong .env. Nguồn lấy từ `evals/golden/<slug>/sources`, truy xuất trong bộ
nhớ (embeddings Gemini), không cần DB. Không có tên thì chạy cả 20 sách.
"""

import json
import sys
from pathlib import Path

from book_review_api.config import get_settings
from book_review_api.providers.llm_gemini import make_embeddings
from book_review_api.providers.llm_writer import make_writer_model
from book_review_api.rag.golden import GoldenBook, load_golden
from book_review_api.rag.memory import InMemoryRetriever
from book_review_api.storyboard.runner import make_storyboard_runner
from book_review_api.storyboard.schema import Storyboard
from book_review_api.storyboard.validate import storyboard_problems

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"


def run(book: GoldenBook, model, embeddings) -> None:  # type: ignore[no-untyped-def]
    print(f"\n=== {book.title}")
    chunks = book.chunks()
    runner = make_storyboard_runner(
        model, InMemoryRetriever(chunks, embeddings), get_settings(), spoiler_free=True
    )
    out = runner(
        {"book": {"title": book.title, "author": book.author, "year": book.year}, "kind": book.kind}
    )
    print("cost:", out.get("cost"))
    if "storyboard" not in out:
        print("THẤT BẠI:", out.get("error_code"))
        return
    sb = Storyboard.model_validate(out["storyboard"])
    problems = storyboard_problems(sb, {c.id: c for c in chunks})
    print(json.dumps(out["storyboard"], ensure_ascii=False, indent=2))
    print("citation hợp lệ" if not problems else f"LỖI citation: {problems}")


def main(slugs: list[str]) -> None:
    books = [b for b in load_golden(GOLDEN) if not slugs or b.slug in slugs]
    settings = get_settings()
    model, embeddings = make_writer_model(settings), make_embeddings(settings)
    for book in books:
        run(book, model, embeddings)


if __name__ == "__main__":
    main(sys.argv[1:])
