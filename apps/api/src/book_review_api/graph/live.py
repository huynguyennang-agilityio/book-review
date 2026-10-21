"""Graph chạy thật cho API: gắn research agent với Gemini, tìm web, kho pgvector (ngày 14).

Các node sau `identify_confirm` vẫn là node rỗng cho tới khi các ngày sau nối vào (storyboard cần
retriever theo sách, media cần worker).
"""

import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.callbacks.manager import dispatch_custom_event
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from book_review_api.agents.research import ResearchRunner, make_research_runner
from book_review_api.agents.tools import (
    Event,
    GeminiSearchProvider,
    SearchProvider,
    TavilySearchProvider,
    ToolContext,
)
from book_review_api.config import Settings
from book_review_api.graph.build import build_graph
from book_review_api.graph.state import BookInput, BookReviewState
from book_review_api.providers.llm_gemini import make_chat_model, make_embeddings
from book_review_api.rag.index import (
    index_chunks,
    make_record_engine,
    make_record_manager,
    make_vector_engine,
    make_vector_store,
)
from book_review_api.rag.retrieve import retrieve

SOURCE_EVENT = "source"


def _publish(event: Event) -> None:
    """Đẩy sự kiện nguồn ra stream AG-UI (event tuỳ biến). Ngoài graph (script) thì bỏ qua."""
    try:
        dispatch_custom_event(SOURCE_EVENT, event)
    except RuntimeError:
        pass


def make_live_research_runner(settings: Settings) -> ResearchRunner:
    model = make_chat_model(settings)
    embeddings = make_embeddings(settings)
    search: SearchProvider = (
        TavilySearchProvider(settings.tavily_api_key)
        if settings.search_provider == "tavily"
        else GeminiSearchProvider(model)
    )
    engine = make_vector_engine(settings.database_url)
    store = make_vector_store(embeddings, engine)
    records = make_record_manager(make_record_engine(settings.database_url))
    book_ids: list[str] = []

    def make_ctx(emit: Callable[[Event], None]) -> ToolContext:
        book_id = str(uuid.uuid4())
        book_ids.append(book_id)

        def on_event(event: Event) -> None:
            emit(event)
            _publish(event)

        return ToolContext(
            search=search,
            index=lambda docs: index_chunks(docs, vector_store=store, record_manager=records)[
                "num_added"
            ],
            retrieve=lambda q: retrieve(
                book_id, q, engine=engine, embeddings=embeddings, settings=settings
            ),
            identity_model=model,
            book_id=book_id,
            emit=on_event,
        )

    inner = make_research_runner(model, make_ctx, settings)

    def run(book: BookInput) -> dict[str, Any]:
        out = inner(book)
        if research := out.get("research"):
            # Ngày sau truy xuất lại đúng kho đã nạp bằng book_id này.
            out["research"] = {**research, "book_id": book_ids[-1]}
        return out

    return run


def build_live_graph(
    settings: Settings, checkpointer: BaseCheckpointSaver[str], store: BaseStore
) -> CompiledStateGraph[BookReviewState]:
    return build_graph(
        checkpointer=checkpointer,
        store=store,
        research_runner=make_live_research_runner(settings),
    )
