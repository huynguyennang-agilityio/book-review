"""Đo độ trễ và chi phí embed 100 chunk (cần GOOGLE_API_KEY thật).

uv run python scripts/measure_embeddings.py [--price-per-m-tokens 0.15]

Lấy chunk từ các trang trong tests/fixtures, lặp lại cho đủ 100 chunk. Số token là ước lượng
của `estimate_tokens`; giá do người chạy nhập theo bảng giá hiện hành của Google.
"""

import argparse
import time
from pathlib import Path

from book_review_api.providers.llm_gemini import make_embeddings
from book_review_api.rag.ingest import ingest_source

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--price-per-m-tokens", type=float, default=None, help="USD / 1M token")
    args = parser.parse_args()

    texts: list[str] = []
    tokens = 0
    while len(texts) < args.count:
        for page in sorted(FIXTURES.glob("*.html")):
            for doc in ingest_source(f"https://example.vn/{page.name}", data=page.read_bytes()):
                if len(texts) < args.count:
                    # Thêm số thứ tự để không trùng chuỗi giữa các vòng lặp.
                    texts.append(f"{doc.page_content}\n\n#{len(texts)}")
                    tokens += int(doc.metadata["token_count"])

    embeddings = make_embeddings()
    start = time.perf_counter()
    vectors = embeddings.embed_documents(texts)
    elapsed = time.perf_counter() - start

    print(f"chunk: {len(texts)}, chiều vector: {len(vectors[0])}")
    print(f"tổng token (ước lượng): {tokens}")
    print(f"thời gian: {elapsed:.2f}s ({elapsed / len(texts) * 1000:.0f} ms/chunk)")
    if args.price_per_m_tokens is not None:
        print(f"chi phí ước tính: ${tokens / 1_000_000 * args.price_per_m_tokens:.5f}")


if __name__ == "__main__":
    main()
