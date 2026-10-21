"""Chạy thật research agent (Gemini + Google Search) cho vài tên sách, in kết quả và chi phí.

    uv run python scripts/run_research.py "Đắc nhân tâm" "Nhà giả kim" "Truyện tu tiên X"

Cần GOOGLE_API_KEY trong .env. Không cần DB: nguồn nạp được chunk rồi đếm, không ghi pgvector.
Bật LangSmith để xem trace: LANGSMITH_TRACING=true và LANGSMITH_API_KEY.
"""

import json
import sys
import uuid
from collections.abc import Callable

from book_review_api.agents.research import make_research_runner
from book_review_api.agents.tools import Event, GeminiSearchProvider, ToolContext
from book_review_api.config import get_settings
from book_review_api.providers.llm_gemini import make_chat_model


def main(titles: list[str]) -> None:
    settings = get_settings()
    model = make_chat_model(settings)

    def make_ctx(emit: Callable[[Event], None]) -> ToolContext:
        return ToolContext(
            search=GeminiSearchProvider(model),
            index=lambda docs: len(docs),
            identity_model=model,
            book_id=str(uuid.uuid4()),
            emit=emit,
        )

    runner = make_research_runner(model, make_ctx, settings)
    for title in titles:
        print(f"\n=== {title}")
        out = runner({"title": title})
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
