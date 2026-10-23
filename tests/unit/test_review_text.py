"""Tab "Từ bài review có sẵn" (ngày 2): kiểm tra bài review ở precheck và rẽ nhánh graph."""

from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from book_review_api.errors import ErrorCode
from book_review_api.graph.build import build_graph
from book_review_api.graph.nodes.precheck import precheck
from book_review_api.graph.nodes.review_text import (
    ReviewInputError,
    clean_user_review,
    review_seconds,
)

# ~120 âm tiết: đủ ngưỡng 100 từ của ý chính.
MAIN = " ".join(
    [
        "Nhà giả kim kể về Santiago, một cậu bé chăn cừu ở Andalusia.",
        "Cậu nhiều lần mơ thấy kho báu nằm gần kim tự tháp Ai Cập.",
        "Cậu bán đàn cừu và lên đường đi tìm giấc mơ của mình.",
    ]
    * 3
)


def review(**fields: Any) -> dict[str, Any]:
    return {"main": MAIN, **fields}


def state(user_review: Any, title: str = "Nhà giả kim") -> Any:
    return {
        "book": {"title": title},
        "options": {"source": "user_review"},
        "user_review": user_review,
    }


def config(thread_id: str = "t1") -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def visited(graph: Any, inp: Any) -> list[str]:
    out: list[str] = []
    for chunk in graph.stream(inp, config(), stream_mode="updates"):
        out.extend(k for k in chunk if not k.startswith("__"))
    return out


# --- Làm sạch và kiểm tra -------------------------------------------------------


def test_clean_keeps_text_and_drops_empty_fields() -> None:
    out = clean_user_review(review(hook="  Bạn có dám   đi theo giấc mơ? ", comment="   "))
    assert out["hook"] == "Bạn có dám đi theo giấc mơ?"
    assert out["comment"] is None
    assert out["main"] == MAIN
    assert out["warnings"] == []
    assert out["pii_masked"] == 0


def test_only_main_is_required() -> None:
    out = clean_user_review({"main": MAIN})
    assert out["hook"] is None and out["comment"] is None


@pytest.mark.parametrize(
    "raw",
    [None, "chuỗi", {}, {"main": ""}, {"main": "Quá ngắn."}, {"main": 123}],
)
def test_short_or_missing_main_is_rejected(raw: Any) -> None:
    with pytest.raises(ReviewInputError) as err:
        clean_user_review(raw)
    assert err.value.code in (ErrorCode.REVIEW_TOO_SHORT, ErrorCode.VALIDATION_ERROR)


def test_main_under_100_words_is_too_short() -> None:
    with pytest.raises(ReviewInputError) as err:
        clean_user_review({"main": "một " * 99})
    assert err.value.code == ErrorCode.REVIEW_TOO_SHORT
    assert clean_user_review({"main": "một " * 100})["main"]


def test_review_longer_than_5_minutes_is_rejected() -> None:
    # 1.200 âm tiết / 3,8 ≈ 316 giây.
    with pytest.raises(ReviewInputError) as err:
        clean_user_review({"main": "một " * 1200})
    assert err.value.code == ErrorCode.REVIEW_TOO_LONG
    # Tính cả hook và nhận xét vào thời lượng.
    with pytest.raises(ReviewInputError):
        clean_user_review({"main": "một " * 1000, "comment": "hai " * 200})


def test_long_hook_warns_but_passes() -> None:
    out = clean_user_review(review(hook="mở " * 25))
    assert out["warnings"] == ["HOOK_LONG"]


def test_pii_is_masked_in_every_field() -> None:
    out = clean_user_review(review(hook="Gọi 0912 345 678 nhé", comment="Mail mình: a.b@gmail.com"))
    assert out["hook"] == "Gọi [PHONE] nhé"
    assert out["comment"] == "Mail mình: [EMAIL]"
    assert out["pii_masked"] == 2


def test_review_seconds_counts_all_fields() -> None:
    one = review_seconds({"main": "một " * 38})
    both = review_seconds({"main": "một " * 38, "hook": "một " * 38})
    assert one == pytest.approx(10.45)
    assert both == pytest.approx(20.9)


# --- Node precheck --------------------------------------------------------------


def test_precheck_stores_cleaned_review() -> None:
    out = precheck(state(review(hook="  Hook  ")))
    assert out["status"] == "running"
    assert out["user_review"]["hook"] == "Hook"


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ({"main": "ngắn"}, "REVIEW_TOO_SHORT"),
        ({"main": "một " * 1200}, "REVIEW_TOO_LONG"),
        (None, "VALIDATION_ERROR"),
        (review(comment="Hay hơn mọi truyện kiếm hiệp"), "GENRE_EXCLUDED"),
    ],
)
def test_precheck_rejects_bad_review(raw: Any, code: str) -> None:
    out = precheck(state(raw))
    assert out == {"status": "rejected", "error_code": code}


def test_precheck_rejects_unknown_source() -> None:
    out = precheck({"book": {"title": "X"}, "options": {"source": "pdf"}})  # type: ignore[typeddict-item]
    assert out["error_code"] == "VALIDATION_ERROR"


def test_book_source_ignores_user_review() -> None:
    out = precheck({"book": {"title": "Nhà giả kim"}, "user_review": None})
    assert out["status"] == "running"
    assert "user_review" not in out


# --- Rẽ nhánh graph -------------------------------------------------------------


def test_user_review_skips_research_and_identify() -> None:
    called: list[Any] = []

    def research(book: Any) -> dict[str, Any]:
        called.append(book)
        return {}

    graph = build_graph(InMemorySaver(), research_runner=research)
    path = visited(graph, state(review()))
    assert path[:3] == ["precheck", "ingest_review", "estimate_cost"]
    assert "research_agent" not in path and "identify_confirm" not in path
    assert called == []
    # Dừng ở màn duyệt kịch bản như tab cũ.
    assert graph.get_state(config()).next == ("review_script",)


def test_book_source_still_runs_research() -> None:
    called: list[Any] = []

    def research(book: Any) -> dict[str, Any]:
        called.append(book)
        return {}

    graph = build_graph(InMemorySaver(), research_runner=research)
    path = visited(graph, {"book": {"title": "Nhà giả kim"}})
    assert path[:3] == ["precheck", "research_agent", "identify_confirm"]
    assert "ingest_review" not in path
    assert len(called) == 1


def test_rejected_review_stops_after_precheck() -> None:
    graph = build_graph(InMemorySaver())
    assert visited(graph, state({"main": "ngắn"})) == ["precheck"]
    values = graph.get_state(config()).values
    assert values["status"] == "rejected"
    assert values["error_code"] == "REVIEW_TOO_SHORT"
