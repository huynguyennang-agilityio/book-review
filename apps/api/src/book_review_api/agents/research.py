"""Research agent: `create_agent` + tools ngày 8 + middleware, kết quả có cấu trúc."""

import logging
from collections.abc import Callable
from typing import Any, Literal

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from book_review_api.agents.middleware import research_middleware
from book_review_api.agents.tools import Event, ToolContext, research_tools
from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.state import BookInput
from book_review_api.prompt_loader import load_prompt as _load_prompt

log = logging.getLogger(__name__)

PROMPT_VERSION = "research_v1"


class BookCandidate(BaseModel):
    title: str
    author: str | None = None
    year: int | None = None
    original_title: str | None = None


class ResearchSource(BaseModel):
    url: str
    title: str = ""


class ResearchResult(BaseModel):
    """Kết quả cuối của agent (structured output)."""

    book: BookCandidate
    kind: Literal["fiction", "non_fiction"]
    genre: str = Field(description="Thể loại cụ thể, vd 'kỹ năng sống', 'tiểu thuyết'")
    candidates: list[BookCandidate] = Field(
        default_factory=list, description="Mọi cuốn trùng tên tìm thấy, rỗng nếu chỉ có một"
    )
    low_confidence: bool = Field(
        default=False, description="True nếu chưa chắc đúng cuốn người dùng muốn"
    )
    sources: list[ResearchSource] = Field(default_factory=list, description="Nguồn đã nạp vào RAG")
    notes: str = ""


def load_prompt(settings: Settings) -> str:
    return _load_prompt(PROMPT_VERSION).format(min_sources=settings.research_min_sources)


def build_research_agent(
    model: BaseChatModel,
    ctx: ToolContext,
    settings: Settings | None = None,
    summarizer: BaseChatModel | None = None,
) -> Any:
    settings = settings or get_settings()
    return create_agent(
        model,
        tools=research_tools(ctx),
        system_prompt=load_prompt(settings),
        middleware=research_middleware(settings, summarizer or model),
        response_format=ResearchResult,
        name="research_agent",
    )


# Hàm chạy một lần research cho một cuốn sách, trả về phần cập nhật cho state của graph.
ResearchRunner = Callable[[BookInput], dict[str, Any]]


def make_research_runner(
    model: BaseChatModel,
    make_ctx: Callable[[Callable[[Event], None]], ToolContext],
    settings: Settings | None = None,
    config: dict[str, Any] | None = None,
) -> ResearchRunner:
    """`make_ctx` nhận hàm `emit` (thu sự kiện nguồn) và trả `ToolContext` đã gắn phụ thuộc."""
    settings = settings or get_settings()

    def run(book: BookInput) -> dict[str, Any]:
        events: list[Event] = []
        agent = build_research_agent(model, make_ctx(events.append), settings)
        ask = f"Sách: {book['title']}"
        if author := book.get("author"):
            ask += (
                f"\nTác giả: {author}\nKhi gọi web_search, dùng dạng "
                f'"{book["title"]}" {author} để ra đúng cuốn. Ưu tiên cuốn đúng tác giả này.'
            )
        state: dict[str, Any] = {"messages": [HumanMessage(ask)]}

        def ingested() -> set[str]:
            return {e["url"] for e in events if e.get("type") == "source_ingested"}

        # Agent hay dừng sớm khi tự thấy "đủ": nhắc tối đa `research_nudges` lần nếu thiếu nguồn.
        for attempt in range(settings.research_nudges + 1):
            out = agent.invoke(state, config=config)
            result: ResearchResult | None = out.get("structured_response")
            if out.get("error_code") or result is None:
                break
            have = len(ingested())
            if have >= settings.research_min_sources or attempt == settings.research_nudges:
                break
            nudge = (
                f"Mới nạp được {have} nguồn bằng ingest_source, cần ít nhất "
                f"{settings.research_min_sources}. Tìm thêm bằng web_search, đọc bằng fetch_page "
                "rồi nạp bằng ingest_source, sau đó trả lại kết quả cuối."
            )
            state = {
                "messages": [*out["messages"], HumanMessage(nudge)],
                "cost_usd": out.get("cost_usd", 0.0),
            }
        # Cộng từ mọi AIMessage: lần gọi model cuối (trả kết quả cuối) không qua lại `after_model`.
        n_in = n_out = 0
        for m in out.get("messages", []):
            if isinstance(m, AIMessage) and m.usage_metadata:
                n_in += m.usage_metadata["input_tokens"]
                n_out += m.usage_metadata["output_tokens"]
        usd = (n_in * settings.price_input_per_mtok + n_out * settings.price_output_per_mtok) / 1e6
        cost = {"usd": usd, "input_tokens": float(n_in), "output_tokens": float(n_out)}
        update: dict[str, Any] = {"cost": cost}
        if code := out.get("error_code"):
            status = "rejected" if code == ErrorCode.GENRE_EXCLUDED.value else "failed"
            return {**update, "status": status, "error_code": code}
        if result is None:  # hết vòng gọi mà chưa có kết quả
            last = out["messages"][-1] if out.get("messages") else None
            log.warning(
                "research không có kết quả cuối; tin nhắn cuối: %r", getattr(last, "content", last)
            )
            return {**update, "status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        urls = ingested()
        titles = {e["url"]: e.get("title", "") for e in events if e.get("title")}
        data = result.model_dump()
        # Nguồn lấy từ sự kiện nạp thật, không tin danh sách agent tự khai.
        data["sources"] = [{"url": u, "title": titles.get(u, "")} for u in sorted(urls)]
        data["ingested_sources"] = len(urls)
        data["min_sources"] = settings.research_min_sources
        data["meets_min_sources"] = len(urls) >= settings.research_min_sources
        data["prompt_version"] = PROMPT_VERSION
        return {**update, "research": data}

    return run
