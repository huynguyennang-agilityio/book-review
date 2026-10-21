"""Graph khung với checkpointer trong bộ nhớ: thứ tự node, interrupt, resume, huỷ."""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from book_review_api.graph.build import NODES, build_graph
from book_review_api.graph.state import BookReviewState, merge_status

PLAN_NODES = [
    "precheck",
    "research_agent",
    "identify_confirm",
    "storyboard",
    "faithfulness_eval",
    "estimate_cost",
    "review_script",
    "tts_align",
    "build_timeline",
    "subtitles",
    "character_sheets",
    "review_characters",
    "scene_images",
    "motion",
    "compose_render",
    "save_memory",
]


def config(thread_id: str = "t1") -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def run(graph: CompiledStateGraph[BookReviewState], inp: Any, thread_id: str = "t1") -> list[str]:
    """Chạy tới khi dừng, trả về tên các node đã chạy xong."""
    visited: list[str] = []
    for chunk in graph.stream(inp, config(thread_id), stream_mode="updates"):
        visited.extend(k for k in chunk if not k.startswith("__"))
    return visited


def test_has_all_plan_nodes() -> None:
    assert list(NODES) == PLAN_NODES
    graph = build_graph()
    assert set(PLAN_NODES) <= set(graph.get_graph().nodes)


def test_rejected_title_stops_after_precheck() -> None:
    graph = build_graph(InMemorySaver())
    assert run(graph, {"book": {"title": "Truyện kiếm hiệp"}}) == ["precheck"]
    state = graph.get_state(config())
    assert state.next == ()
    assert state.values["status"] == "rejected"
    assert state.values["error_code"] == "GENRE_EXCLUDED"


def test_pause_and_resume_to_end() -> None:
    graph = build_graph(InMemorySaver())
    first = run(graph, {"book": {"title": "Nhà giả kim"}})
    assert first == PLAN_NODES[:6]
    paused = graph.get_state(config())
    assert paused.next == ("review_script",)
    assert paused.interrupts[0].value["type"] == "review_script"

    second = run(graph, Command(resume={"approved": True}))
    assert second[0] == "review_script"
    paused = graph.get_state(config())
    assert paused.next == ("review_characters",)

    third = run(graph, Command(resume={"approved": True}))
    assert third[-3:] == ["motion", "compose_render", "save_memory"]
    done = graph.get_state(config())
    assert done.next == ()
    assert done.values["status"] == "done"
    # Mọi node của plan đã chạy đúng một lần (node chạy cùng bước với interrupt được lưu
    # thành pending write nên có thể xuất hiện lại dưới dạng cache).
    assert set(first + second + third) == set(PLAN_NODES)


def test_cancel_while_waiting_for_review() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}})
    graph.update_state(config(), {"cancel_requested": True})
    assert run(graph, Command(resume={"approved": True})) == ["review_script"]
    state = graph.get_state(config())
    assert state.next == ()
    assert state.values["status"] == "cancelled"
    assert state.values["error_code"] == "CANCELLED"
    assert state.values["error_code"] == "CANCELLED"


def test_cancel_from_review_in_parallel_branch() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}})
    run(graph, Command(resume={"approved": True}))
    assert graph.get_state(config()).next == ("review_characters",)
    visited = run(graph, Command(resume={"cancel": True}))
    assert "compose_render" not in visited
    assert "save_memory" not in visited
    state = graph.get_state(config())
    assert state.next == ()
    assert state.values["status"] == "cancelled"
    assert state.values["error_code"] == "CANCELLED"


def test_status_reducer_keeps_terminal() -> None:
    assert merge_status("cancelled", "running") == "cancelled"
    assert merge_status("running", "cancelled") == "cancelled"
    assert merge_status("running", "done") == "done"
    assert merge_status(None, "running") == "running"
