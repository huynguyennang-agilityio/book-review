"""Phần thuần của retrieve: tsquery, RRF, LLM reranker, chọn reranker theo config."""

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from book_review_api.config import Settings
from book_review_api.rag.retrieve import (
    Chunk,
    LLMReranker,
    fulltext_query,
    make_reranker,
    rrf_merge,
)


def c(i: str) -> Chunk:
    return Chunk(id=i, content=f"nội dung {i}")


def test_fulltext_query_is_or_of_safe_words() -> None:
    assert fulltext_query("Fatima là ai?") == "fatima | là | ai"
    assert fulltext_query("Đắc Nhân Tâm Đắc") == "đắc | nhân | tâm"
    assert fulltext_query("a' & !( | :* <->") == "a"
    assert fulltext_query("?!  ") is None


def test_rrf_prefers_chunks_ranked_by_both_lists() -> None:
    merged = rrf_merge([[c("a"), c("b"), c("c")], [c("c"), c("d")]])
    assert [m.id for m in merged] == ["c", "a", "b", "d"]
    assert merged[0].score == pytest.approx(1 / 63 + 1 / 61)


def test_rrf_empty_and_single_list() -> None:
    assert rrf_merge([[], []]) == []
    assert [m.id for m in rrf_merge([[c("x"), c("y")], []])] == ["x", "y"]


def _rerank(reply: str, n: int = 2) -> list[str]:
    model = FakeListChatModel(responses=[reply])
    return [x.id for x in LLMReranker(model).rerank("q", [c("a"), c("b"), c("c")], n)]


def test_llm_reranker_orders_by_reply() -> None:
    assert _rerank("[2, 0, 1]") == ["c", "a"]
    assert _rerank("Thứ tự: [1,2]", n=3) == ["b", "c", "a"]  # chỉ số thiếu thì nối phía sau


def test_llm_reranker_ignores_bad_indices_and_falls_back() -> None:
    assert _rerank("[9, -1, 1, 1]") == ["b", "a"]
    assert _rerank("không biết") == ["a", "b"]


def test_llm_reranker_falls_back_on_model_error() -> None:
    class Boom(FakeListChatModel):
        def _call(self, *a: Any, **k: Any) -> str:
            raise RuntimeError("quota")

    assert [x.id for x in LLMReranker(Boom(responses=["x"])).rerank("q", [c("a"), c("b")], 1)] == [
        "a"
    ]


def test_make_reranker_by_config() -> None:
    assert make_reranker(Settings(rerank_provider="none")) is None
    with pytest.raises(ValueError):
        make_reranker(Settings(rerank_provider="khong-co"))
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        make_reranker(Settings(rerank_provider="llm", google_api_key=""))
