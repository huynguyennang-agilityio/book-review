"""Bộ nhớ dài hạn (store, node save_memory, precheck áp dụng sở thích) và loader prompt."""

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from book_review_api.graph.build import build_graph
from book_review_api.graph.state import BookReviewState
from book_review_api.memory.store import (
    DEFAULT_PREFERENCES,
    apply_preferences,
    delete_memory,
    export_memory,
    load_preferences,
    record_run,
    save_preferences,
)
from book_review_api.prompt_loader import ACTIVE_PROMPTS, load_prompt, prompt_version_label

USER = "user-1"


def test_preferences_roundtrip_and_filter() -> None:
    store = InMemoryStore()
    assert load_preferences(store, USER) == {}
    save_preferences(store, USER, {"voice": "vi-VN-NamMinhNeural", "bogus": 1})
    save_preferences(store, USER, {"length_minutes": 5})
    assert load_preferences(store, USER) == {"voice": "vi-VN-NamMinhNeural", "length_minutes": 5}


def test_apply_preferences_keeps_user_choice() -> None:
    prefs = {"voice": "nam", "length_minutes": 5, "no_spoiler": False}
    assert apply_preferences({}, prefs) == {"voice": "nam", "minutes": 5, "no_spoiler": False}
    assert apply_preferences({"voice": "nu"}, prefs)["voice"] == "nu"
    assert apply_preferences({}, {"voice": "default"}) == {}


def test_record_export_delete() -> None:
    store = InMemoryStore()
    record_run(
        store,
        USER,
        thread_id="t1",
        book={"title": "Đắc nhân tâm", "author": "Dale Carnegie"},
        options={"voice": "nam", "minutes": 2, "budget_usd": 1},
        characters={"an": {"name": "An", "sheet_path": "x.png"}},
        feedback=[{"type": "script_edit", "scenes": 2}],
    )
    mem = export_memory(store, USER)
    assert mem["preferences"]["voice"] == "nam"
    assert mem["preferences"]["tone"] == DEFAULT_PREFERENCES["tone"]
    assert mem["books"][0]["title"] == "Đắc nhân tâm"
    assert mem["characters"][0]["name"] == "An"
    assert mem["feedback"][0]["items"] == [{"type": "script_edit", "scenes": 2}]
    assert export_memory(store, "other")["books"] == []
    assert delete_memory(store, USER) == 4
    assert export_memory(store, USER)["books"] == []
    assert load_preferences(store, USER) == {}


def _cfg(thread_id: str, user: str | None = USER) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "user_id": user}}


def _finish(
    graph: CompiledStateGraph[BookReviewState], inp: BookReviewState, cfg: RunnableConfig
) -> None:
    """Chạy graph khung qua hai điểm duyệt (kịch bản, nhân vật) tới `save_memory`."""
    graph.invoke(inp, cfg)
    graph.invoke(Command(resume={"approved": True}), cfg)
    graph.invoke(Command(resume={"approved": True}), cfg)


def test_second_run_applies_saved_preferences() -> None:
    store = InMemoryStore()
    graph = build_graph(checkpointer=InMemorySaver(), store=store)
    first: BookReviewState = {
        "book": {"title": "Sapiens"},
        "options": {"voice": "nam", "minutes": 5},
    }
    _finish(graph, first, _cfg("a"))
    assert load_preferences(store, USER) == {"voice": "nam", "length_minutes": 5}
    assert export_memory(store, USER)["books"][0]["title"] == "Sapiens"

    second: BookReviewState = {"book": {"title": "Atomic Habits"}, "options": {}}
    graph.invoke(second, _cfg("b"))
    values = graph.get_state(_cfg("b")).values
    assert values["options"] == {"voice": "nam", "minutes": 5}
    assert values["preferences_applied"] == ["minutes", "voice"]


def test_no_user_id_skips_memory() -> None:
    store = InMemoryStore()
    graph = build_graph(checkpointer=InMemorySaver(), store=store)
    inp: BookReviewState = {"book": {"title": "Sapiens"}, "options": {"voice": "nam"}}
    _finish(graph, inp, _cfg("c", None))
    assert store.search(("users",)) == []


def test_prompt_loader_versions() -> None:
    for version in ACTIVE_PROMPTS.values():
        assert load_prompt(version).strip()
    assert "storyboard_v1" in prompt_version_label()
    with pytest.raises(FileNotFoundError):
        load_prompt("khong_co_v9")


def test_memory_api_get_put_delete() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from book_review_api import memory_api
    from book_review_api.auth import CurrentUser, current_user

    app = FastAPI()
    app.include_router(memory_api.router)
    app.state.store = InMemoryStore()
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        user_id=USER, email=None, role=None
    )
    client = TestClient(app)

    assert client.get("/me/memory").json()["preferences"] == DEFAULT_PREFERENCES
    body = client.put("/me/memory/preferences", json={"voice": "nam", "no_spoiler": False}).json()
    assert body["preferences"]["voice"] == "nam"
    assert body["preferences"]["no_spoiler"] is False
    assert client.delete("/me/memory").json() == {"deleted": 1}
    assert client.get("/me/memory").json()["preferences"] == DEFAULT_PREFERENCES
