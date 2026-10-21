"""Chạy thật storyboard (Gemini) rồi node `character_sheets` (Fal) cho sách golden.

    uv run python scripts/run_characters.py nha-gia-kim hoang-tu-be

Cần GOOGLE_API_KEY và FAL_KEY trong .env. Mỗi nhân vật chính 4 ứng viên (~0,03 USD/ảnh).
Ảnh ghi vào `<MEDIA_DIR>/characters/`; in đường dẫn và chi phí.
"""

import sys
from pathlib import Path
from typing import Any

from book_review_api.config import get_settings
from book_review_api.graph.nodes.characters import make_character_sheets_node
from book_review_api.graph.state import BookReviewState
from book_review_api.providers.image_fal import FalImageProvider
from book_review_api.providers.llm_gemini import make_chat_model, make_embeddings
from book_review_api.rag.golden import load_golden
from book_review_api.rag.memory import InMemoryRetriever
from book_review_api.storyboard.runner import make_storyboard_runner

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"


def main(slugs: list[str]) -> None:
    settings = get_settings()
    if not settings.fal_key:
        sys.exit("Thiếu FAL_KEY")
    model, embeddings = make_chat_model(settings), make_embeddings(settings)
    provider = FalImageProvider(settings.fal_key, concurrency=settings.fal_concurrency)
    node = make_character_sheets_node(provider, settings, approved_lookup=lambda s, n: None)
    total = 0.0
    for book in (b for b in load_golden(GOLDEN) if not slugs or b.slug in slugs):
        print(f"\n=== {book.title}")
        runner = make_storyboard_runner(
            model, InMemoryRetriever(book.chunks(), embeddings), settings, spoiler_free=True
        )
        out = runner(
            {
                "book": {"title": book.title, "author": book.author, "year": book.year},
                "kind": book.kind,
            }
        )
        if "storyboard" not in out:
            print("storyboard thất bại:", out.get("error_code"))
            continue
        state: BookReviewState = {"storyboard": out["storyboard"], "cost": out.get("cost", {})}
        res: dict[str, Any] = node(state)
        for slug, cand in res.get("character_candidates", {}).items():
            print(f"- {cand['name']} ({slug}): {len(cand['images'])} ảnh")
            for p in cand["images"]:
                print("   ", (Path(settings.media_dir) / p).resolve())
        print("trạng thái:", res.get("status", "ok"), res.get("error_code", ""))
        print("chi phí ảnh:", res.get("cost"))
        total += res.get("cost", {}).get("usd", 0.0)
    print(f"\nTổng chi phí ảnh: {total:.2f} USD")


if __name__ == "__main__":
    main(sys.argv[1:])
