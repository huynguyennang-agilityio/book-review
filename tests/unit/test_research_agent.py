"""Research agent với model giả theo kịch bản: middleware, kết quả có cấu trúc, node xác nhận."""

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeListChatModel, GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from book_review_api.agents.research import ResearchResult, make_research_runner
from book_review_api.agents.tools import Event, SearchResult, ToolContext
from book_review_api.config import Settings
from book_review_api.graph.build import build_graph
from book_review_api.graph.state import BookInput
from book_review_api.rag.ingest import Document

PAGE = (
    "<html><head><title>T</title></head><body><article><p>"
    + ("Nội dung giới thiệu cuốn sách rất dài. " * 30)
    + "</p></article></body></html>"
)


class ScriptedModel(GenericFakeChatModel):
    """Phát lại các AIMessage theo thứ tự; `bind_tools` bỏ qua vì kịch bản đã có tool_calls."""

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
        return self

    def with_structured_output(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


def call(name: str, args: dict[str, Any], id_: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id_}])


def usage(msg: AIMessage, n_in: int = 1000, n_out: int = 100) -> AIMessage:
    msg.usage_metadata = {
        "input_tokens": n_in,
        "output_tokens": n_out,
        "total_tokens": n_in + n_out,
    }
    return msg


class FakeSearch:
    def search(self, query: str) -> list[SearchResult]:
        return [SearchResult(f"https://s{i}.vn/x", f"S{i}") for i in range(5)]


def make_ctx(emit: Callable[[Event], None], identity: str = "") -> ToolContext:
    return ToolContext(
        search=FakeSearch(),
        fetch=lambda url: PAGE,
        url_allowed=lambda _u: True,
        index=lambda docs: len(docs),
        book_id="b1",
        identity_model=FakeListChatModel(responses=[identity]),
        emit=emit,
    )


def final(book: str, **kw: Any) -> AIMessage:
    payload = {
        "book": {"title": book},
        "kind": "non_fiction",
        "genre": "kỹ năng sống",
        "sources": [{"url": "https://s0.vn/x"}],
        **kw,
    }
    return call("ResearchResult", payload, "final")


def runner_for(
    script: list[AIMessage], identity: str = '{"candidates": []}', **settings: Any
) -> Callable[..., dict[str, Any]]:
    settings.setdefault("research_nudges", 0)  # không nhắc lại, trừ test nudge
    model = ScriptedModel(messages=iter(script))
    return make_research_runner(
        model,
        lambda emit: make_ctx(emit, identity),
        Settings(**settings),
    )


def test_agent_ingests_sources_and_returns_structured_result() -> None:
    script = [
        usage(call("ingest_source", {"url": f"https://s{i}.vn/x", "text": PAGE}, f"c{i}"))
        for i in range(4)
    ]
    script.append(usage(final("Đắc nhân tâm")))
    out = runner_for(script)({"title": "Đắc nhân tâm"})
    assert out["research"]["book"]["title"] == "Đắc nhân tâm"
    assert out["research"]["ingested_sources"] == 4
    assert out["research"]["meets_min_sources"] is True
    assert out["research"]["prompt_version"] == "research_v1"
    assert out["cost"]["input_tokens"] == 5000
    assert out["cost"]["usd"] > 0
    ResearchResult.model_validate(
        {k: v for k, v in out["research"].items() if k in ResearchResult.model_fields}
    )


def test_excluded_genre_stops_with_genre_excluded() -> None:
    script = [
        usage(call("check_genre", {"genre": "tiên hiệp"}, "g1")),
        usage(call("web_search", {"query": "không được chạy"}, "w1")),
    ]
    out = runner_for(script)({"title": "Một bộ truyện"})
    assert out["status"] == "rejected"
    assert out["error_code"] == "GENRE_EXCLUDED"
    assert "research" not in out


def test_budget_exceeded_stops_agent() -> None:
    script = [
        usage(call("web_search", {"query": "a"}, "w1"), 1_000_000, 0),
        usage(call("web_search", {"query": "b"}, "w2")),
    ]
    out = runner_for(script, research_budget_usd=0.1)({"title": "X"})
    assert out["status"] == "failed"
    assert out["error_code"] == "BUDGET_EXCEEDED"


def test_model_call_limit_ends_without_result() -> None:
    script = [usage(call("web_search", {"query": str(i)}, f"w{i}")) for i in range(5)]
    out = runner_for(script, research_model_call_limit=2)({"title": "X"})
    assert out["status"] == "failed"
    assert out["error_code"] == "INTERNAL_ERROR"


def cfg(thread: str = "t") -> RunnableConfig:
    return {"configurable": {"thread_id": thread}}


def test_ambiguous_book_interrupts_and_resume_picks_candidate() -> None:
    two = [{"title": "Nhà giả kim", "year": 1988}, {"title": "Nhà giả kim", "year": 2010}]
    runner = runner_for([usage(final("Nhà giả kim", candidates=two, low_confidence=True))])
    graph = build_graph(InMemorySaver(), research_runner=runner)
    graph.invoke({"book": {"title": "Nhà giả kim"}}, cfg())
    state = graph.get_state(cfg())
    assert state.next == ("identify_confirm",)
    payload = state.tasks[0].interrupts[0].value
    assert payload["type"] == "identify_confirm" and len(payload["candidates"]) == 2
    graph.invoke(Command(resume={"index": 1}), cfg())
    state = graph.get_state(cfg())
    assert state.next == ("review_script",)
    assert state.values["research"]["book"]["year"] == 2010
    assert state.values["research"]["low_confidence"] is False


def test_clear_book_skips_confirmation() -> None:
    runner = runner_for([usage(final("Đắc nhân tâm"))])
    graph = build_graph(InMemorySaver(), research_runner=runner)
    graph.invoke({"book": {"title": "Đắc nhân tâm"}}, cfg("c"))
    assert graph.get_state(cfg("c")).next == ("review_script",)


def test_rejected_by_agent_stops_graph() -> None:
    script = [usage(call("check_genre", {"genre": "kiếm hiệp"}, "g"))]
    graph = build_graph(InMemorySaver(), research_runner=runner_for(script))
    out = graph.invoke({"book": {"title": "Một bộ truyện"}}, cfg("r"))
    assert out["status"] == "rejected" and out["error_code"] == "GENRE_EXCLUDED"
    assert graph.get_state(cfg("r")).next == ()


def test_cancel_during_confirm() -> None:
    two = [{"title": "A"}, {"title": "B"}]
    runner = runner_for([usage(final("A", candidates=two))])
    graph = build_graph(InMemorySaver(), research_runner=runner)
    graph.invoke({"book": {"title": "A"}}, cfg("x"))
    out = graph.invoke(Command(resume={"cancel": True}), cfg("x"))
    assert out["status"] == "cancelled"


_ = (BaseMessage, BaseTool, Document)


def test_nudge_when_agent_stops_with_too_few_sources() -> None:
    def ingest(i: int) -> AIMessage:
        return usage(call("ingest_source", {"url": f"https://s{i}.vn/x", "text": PAGE}, f"c{i}"))

    script = [ingest(0), usage(final("X")), ingest(1), ingest(2), ingest(3), usage(final("X"))]
    out = runner_for(script, research_nudges=2)({"title": "X"})
    assert out["research"]["ingested_sources"] == 4
    assert out["research"]["meets_min_sources"] is True
    assert len(out["research"]["sources"]) == 4


def test_gives_up_after_max_nudges_and_reports_shortfall() -> None:
    script = [usage(final("X")), usage(final("X")), usage(final("X"))]
    out = runner_for(script, research_nudges=2)({"title": "X"})
    assert out["research"]["ingested_sources"] == 0
    assert out["research"]["meets_min_sources"] is False


TWO_SAME_TITLE = [
    {"title": "Đời", "author": "Nguyễn An"},
    {"title": "Đời", "author": "Trần Bình"},
]


def run_graph(book: BookInput, thread: str, **final_kw: Any) -> Any:
    runner = runner_for([usage(final(book["title"], **final_kw))])
    graph = build_graph(InMemorySaver(), research_runner=runner)
    graph.invoke({"book": book}, cfg(thread))
    return graph, graph.get_state(cfg(thread))


def test_author_picks_matching_candidate_without_asking() -> None:
    _, state = run_graph(
        {"title": "Đời", "author": "tran binh"},
        "a1",
        candidates=TWO_SAME_TITLE,
        low_confidence=True,
    )
    assert state.next == ("review_script",)
    assert state.values["research"]["book"]["author"] == "Trần Bình"
    assert state.values["research"]["low_confidence"] is False


def test_wrong_author_asks_with_warning() -> None:
    _, state = run_graph({"title": "Đời", "author": "Lê Cường"}, "a2", candidates=TWO_SAME_TITLE)
    assert state.next == ("identify_confirm",)
    assert "Lê Cường" in state.tasks[0].interrupts[0].value["message"]


def test_without_author_behaviour_unchanged() -> None:
    _, state = run_graph({"title": "Đời"}, "a3", candidates=TWO_SAME_TITLE)
    assert state.next == ("identify_confirm",)
    assert "tác giả" not in state.tasks[0].interrupts[0].value["message"]


def test_author_goes_into_search_hint() -> None:
    seen: list[str] = []
    model = ScriptedModel(messages=iter([usage(final("Đời"))]))
    orig = model.invoke

    def spy(inp: Any, *a: Any, **k: Any) -> Any:
        seen.append(str(inp))
        return orig(inp, *a, **k)

    object.__setattr__(model, "invoke", spy)
    make_research_runner(model, lambda emit: make_ctx(emit), Settings(research_nudges=0))(
        {"title": "Đời", "author": "Nguyễn An"}
    )
    assert any('"Đời" Nguyễn An' in s for s in seen)
