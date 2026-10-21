"""Tools của research agent: nhánh thành công và nhánh lỗi, dùng mock provider."""

from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.store.memory import InMemoryStore

from book_review_api.agents.tools import (
    DEFAULT_PREFERENCES,
    SearchResult,
    ToolContext,
    check_genre,
    fetch_page,
    get_user_preferences,
    ingest_source,
    lookup_book_identity,
    research_tools,
    search_knowledge,
    web_search,
)
from book_review_api.rag.ingest import Document
from book_review_api.rag.retrieve import Chunk

HTML = (
    "<html><head><title>Đắc nhân tâm</title></head><body><article><p>"
    + ("Cuốn sách dạy cách ứng xử và giao tiếp với mọi người. " * 20)
    + "</p></article></body></html>"
)


class FakeSearch:
    def __init__(self, results: list[SearchResult] | Exception) -> None:
        self.results = results

    def search(self, query: str) -> list[SearchResult]:
        if isinstance(self.results, Exception):
            raise self.results
        return self.results


def ctx_with(**kw: Any) -> tuple[ToolContext, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    kw.setdefault("url_allowed", lambda _u: True)
    return ToolContext(emit=events.append, **kw), events


def test_web_search_dedupes_and_emits() -> None:
    rs = [
        SearchResult("https://a.vn", "A"),
        SearchResult("https://a.vn", "A2"),
        SearchResult("https://b.vn", "B"),
    ]
    ctx, events = ctx_with(search=FakeSearch(rs))
    out = web_search(ctx, "đắc nhân tâm review")
    assert [r["url"] for r in out["results"]] == ["https://a.vn", "https://b.vn"]
    assert [e["type"] for e in events] == ["source_found", "source_found"]


def test_web_search_errors() -> None:
    assert web_search(ToolContext(), "x")["error_code"] == "PROVIDER_UNAVAILABLE"
    ctx, _ = ctx_with(search=FakeSearch(RuntimeError("quota")))
    assert web_search(ctx, "x")["error_code"] == "PROVIDER_UNAVAILABLE"
    ctx, _ = ctx_with(search=FakeSearch([]))
    assert web_search(ctx, "  ")["error_code"] == "VALIDATION_ERROR"


def test_fetch_page_ok_and_events() -> None:
    ctx, events = ctx_with(fetch=lambda _u: HTML)
    out = fetch_page(ctx, "https://example.vn/x")
    assert out["title"] == "Đắc nhân tâm" and "giao tiếp" in out["text"]
    assert events[0]["type"] == "source_read"


def test_fetch_page_errors() -> None:
    ctx, _ = ctx_with(fetch=lambda _u: None)
    assert fetch_page(ctx, "https://example.vn")["error_code"] == "NOT_FOUND"
    ctx, _ = ctx_with(fetch=lambda _u: "<html><body></body></html>")
    assert fetch_page(ctx, "https://example.vn")["error_code"] == "NOT_FOUND"

    def boom(_u: str) -> str:
        raise OSError("net")

    ctx, _ = ctx_with(fetch=boom)
    assert fetch_page(ctx, "https://example.vn")["error_code"] == "PROVIDER_UNAVAILABLE"
    assert fetch_page(ToolContext(), "http://127.0.0.1/admin")["error_code"] == "VALIDATION_ERROR"
    assert fetch_page(ToolContext(), "file:///etc/passwd")["error_code"] == "VALIDATION_ERROR"


def test_ingest_source_ok_and_errors() -> None:
    seen: list[Sequence[Document]] = []

    def index(docs: Sequence[Document]) -> int:
        seen.append(docs)
        return len(docs)

    ctx, events = ctx_with(index=index, book_id="b1")
    out = ingest_source(ctx, "https://example.vn/x", "Nội dung đủ dài để thành chunk. " * 30)
    assert out["chunks"] >= 1 and out["added"] == out["chunks"]
    assert seen[0][0].metadata["book_id"] == "b1"
    assert events[0]["type"] == "source_ingested"

    assert ingest_source(ctx, "https://example.vn/x", "  ")["error_code"] == "VALIDATION_ERROR"
    assert ingest_source(ToolContext(), "u", "t")["error_code"] == "PROVIDER_UNAVAILABLE"

    def boom(_d: Sequence[Document]) -> int:
        raise RuntimeError("db")

    ctx, _ = ctx_with(index=boom, book_id="b1")
    assert ingest_source(ctx, "https://x.vn", "abc def")["error_code"] == "INTERNAL_ERROR"


def test_search_knowledge() -> None:
    chunk = Chunk(id="1", content="kết truyện", metadata={"url": "https://a.vn", "title": "A"})
    ctx, _ = ctx_with(retrieve=lambda _q: [chunk])
    out = search_knowledge(ctx, "kết truyện")
    assert out["results"][0]["chunk_id"] == "1" and out["results"][0]["url"] == "https://a.vn"
    assert search_knowledge(ToolContext(), "q")["error_code"] == "PROVIDER_UNAVAILABLE"

    def boom(_q: str) -> list[Chunk]:
        raise RuntimeError("db")

    ctx, _ = ctx_with(retrieve=boom)
    assert search_knowledge(ctx, "q")["error_code"] == "PROVIDER_UNAVAILABLE"


def _identity(reply: str) -> ToolContext:
    return ToolContext(identity_model=FakeListChatModel(responses=[reply]))


def test_lookup_identity_single_and_ambiguous() -> None:
    one = '{"candidates": [{"title": "Đắc nhân tâm", "author": "Dale Carnegie", "year": 1936}]}'
    out = lookup_book_identity(_identity(one), "Đắc nhân tâm")
    assert out["ambiguous"] is False and out["candidates"][0]["author"] == "Dale Carnegie"
    two = 'Kết quả: {"candidates": [{"title": "X", "author": "A"}, {"title": "X", "author": "B"}]}'
    assert lookup_book_identity(_identity(two), "X")["ambiguous"] is True


def test_lookup_identity_errors() -> None:
    assert lookup_book_identity(_identity('{"candidates": []}'), "zzz")["error_code"] == (
        "BOOK_NOT_FOUND"
    )
    assert lookup_book_identity(_identity("không phải json"), "x")["error_code"] == (
        "BOOK_NOT_FOUND"
    )
    assert lookup_book_identity(_identity("{bad}"), "x")["error_code"] == "PROVIDER_UNAVAILABLE"
    assert lookup_book_identity(ToolContext(), "x")["error_code"] == "PROVIDER_UNAVAILABLE"
    assert lookup_book_identity(_identity("{}"), " ")["error_code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("genre", ["Tiên hiệp", "kiem hiep", "Wuxia", "huyền huyễn tu tiên"])
def test_check_genre_excluded(genre: str) -> None:
    out = check_genre(ToolContext(), genre)
    assert out["excluded"] is True and out["error_code"] == "GENRE_EXCLUDED"


def test_check_genre_allowed_and_empty() -> None:
    assert check_genre(ToolContext(), "Self-help") == {"genre": "Self-help", "excluded": False}
    assert check_genre(ToolContext(), "")["error_code"] == "VALIDATION_ERROR"


def test_user_preferences_default_and_store() -> None:
    assert get_user_preferences(ToolContext())["source"] == "default"
    store = InMemoryStore()
    ctx = ToolContext(store=store, user_id="u1")
    assert get_user_preferences(ctx) == {"preferences": DEFAULT_PREFERENCES, "source": "default"}
    store.put(("users", "u1", "preferences"), "default", {"voice": "nam", "junk": 1})
    out = get_user_preferences(ctx)
    assert out["source"] == "store" and out["preferences"]["voice"] == "nam"
    assert "junk" not in out["preferences"]
    # người khác không thấy
    assert get_user_preferences(ToolContext(store=store, user_id="u2"))["source"] == "default"


def test_user_preferences_store_error() -> None:
    class Broken(InMemoryStore):
        def get(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("db")

    out = get_user_preferences(ToolContext(store=Broken(), user_id="u1"))
    assert out["error_code"] == "INTERNAL_ERROR"


def test_langchain_tools_expose_seven_and_never_raise() -> None:
    tools = research_tools(ToolContext())
    assert {t.name for t in tools} == {
        "web_search",
        "fetch_page",
        "ingest_source",
        "search_knowledge",
        "lookup_book_identity",
        "check_genre",
        "get_user_preferences",
    }
    by = {t.name: t for t in tools}
    assert by["web_search"].invoke({"query": "x"})["error_code"] == "PROVIDER_UNAVAILABLE"
    assert by["check_genre"].invoke({"genre": "tiên hiệp"})["excluded"] is True
    assert by["get_user_preferences"].invoke({})["source"] == "default"


def test_tavily_provider_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import json

    from book_review_api.agents.tools import TavilySearchProvider

    payload = {"results": [{"url": "https://a.vn", "title": "A", "content": "nd"}, {"title": "x"}]}
    seen: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: float) -> io.BytesIO:
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data)
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = TavilySearchProvider("k").search("lão hạc")
    assert out == [SearchResult("https://a.vn", "A", "nd")]
    assert seen["auth"] == "Bearer k" and seen["body"]["query"] == "lão hạc"
