"""Graph chạy thật cho API: research agent (ngày 14), storyboard, faithfulness và media qua worker
(ngày 15). Các node sau `review_script` chỉ chạy khi người dùng duyệt.

Node `character_sheets`, `review_characters`, `motion` ảnh thật còn là phần của các ngày sau.
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
from book_review_api.cancel import CancelFlags
from book_review_api.config import Settings
from book_review_api.graph.build import build_graph
from book_review_api.graph.state import BookInput, BookReviewState
from book_review_api.providers.image_fal import FalImageProvider
from book_review_api.providers.llm_gemini import (
    make_chat_model,
    make_embeddings,
    make_judge_model,
)
from book_review_api.providers.llm_writer import make_writer_model
from book_review_api.queue import ArqJobRunner
from book_review_api.rag.index import (
    index_chunks,
    make_record_engine,
    make_record_manager,
    make_vector_engine,
    make_vector_store,
)
from book_review_api.rag.retrieve import Chunk, chunks_by_id, retrieve
from book_review_api.storyboard.faithfulness import make_faithfulness_runner
from book_review_api.storyboard.images import make_prompt_writer
from book_review_api.storyboard.rewrite import SceneRewriter, make_scene_rewriter
from book_review_api.storyboard.runner import StoryboardRunner, make_storyboard_runner

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


def make_live_storyboard_runner(settings: Settings) -> StoryboardRunner:
    """Storyboard cho sách vừa nghiên cứu: truy xuất đúng kho của `research["book_id"]`."""
    model = make_writer_model(settings)
    embeddings = make_embeddings(settings)
    engine = make_vector_engine(settings.database_url)

    def run(research: dict[str, Any]) -> dict[str, Any]:
        options = research.get("options") or {}
        cfg = settings
        if isinstance(options.get("minutes"), int):
            cfg = settings.model_copy(update={"storyboard_minutes": options["minutes"]})
        book_id = str(research["book_id"])
        runner = make_storyboard_runner(
            model,
            lambda q: retrieve(book_id, q, engine=engine, embeddings=embeddings, settings=cfg),
            cfg,
            spoiler_free=bool(options.get("no_spoiler", True)),
        )
        return runner(research)

    return run


def make_live_scene_rewriter(settings: Settings) -> SceneRewriter:
    engine = make_vector_engine(settings.database_url)
    return make_scene_rewriter(
        make_writer_model(settings),
        make_judge_model(settings),
        lambda ids: chunks_by_id(engine, list(ids)),
        settings,
    )


def source_info(chunks: dict[str, Chunk]) -> dict[str, dict[str, Any]]:
    """`source_id` -> url và tiêu đề, lấy từ metadata của các chunk được trích."""
    out: dict[str, dict[str, Any]] = {}
    for c in chunks.values():
        sid = c.metadata.get("source_id")
        if sid and sid not in out:
            out[sid] = {"url": c.metadata.get("url"), "title": c.metadata.get("title")}
    return out


def build_live_graph(
    settings: Settings,
    checkpointer: BaseCheckpointSaver[str],
    store: BaseStore,
    cancel_flags: CancelFlags | None = None,
) -> CompiledStateGraph[BookReviewState]:
    engine = make_vector_engine(settings.database_url)
    return build_graph(
        checkpointer=checkpointer,
        store=store,
        research_runner=make_live_research_runner(settings),
        storyboard_runner=make_live_storyboard_runner(settings),
        faithfulness_runner=make_faithfulness_runner(
            make_judge_model(settings),
            make_writer_model(settings),
            lambda ids: chunks_by_id(engine, list(ids)),
            settings,
        ),
        source_lookup=lambda chunk_ids: source_info(chunks_by_id(engine, list(chunk_ids))),
        job_runner=ArqJobRunner(settings.redis_url, settings.job_timeout_s, cancel_flags),
        cancel_flags=cancel_flags,
        image_provider=(
            FalImageProvider(settings.fal_key, concurrency=settings.fal_concurrency)
            if settings.fal_key
            else None
        ),
        prompt_writer=make_prompt_writer(make_chat_model(settings)),
    )
