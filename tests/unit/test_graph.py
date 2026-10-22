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
    "choose_image_mode",
    "tts_align",
    "build_timeline",
    "subtitles",
    "character_sheets",
    "review_characters",
    "scene_images",
    "manual_images",
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
    assert paused.next == ("choose_image_mode",)
    assert paused.interrupts[0].value["type"] == "choose_image_mode"

    third = run(graph, Command(resume={"mode": "auto"}))
    assert graph.get_state(config()).next == ("review_characters",)
    assert graph.get_state(config()).values["options"]["image_mode"] == "auto"

    fourth = run(graph, Command(resume={"approved": True}))
    assert fourth[-3:] == ["motion", "compose_render", "save_memory"]
    done = graph.get_state(config())
    assert done.next == ()
    assert done.values["status"] == "done"
    # Auto đi đúng đường cũ: mọi node của plan chạy, trừ nhánh manual.
    # (node chạy cùng bước với interrupt được lưu thành pending write nên có thể xuất hiện lại.)
    assert set(first + second + third + fourth) == set(PLAN_NODES) - {"manual_images"}


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
    run(graph, Command(resume={"mode": "auto"}))
    assert graph.get_state(config()).next == ("review_characters",)
    visited = run(graph, Command(resume={"cancel": True}))
    assert "compose_render" not in visited
    assert "save_memory" not in visited
    state = graph.get_state(config())
    assert state.next == ()
    assert state.values["status"] == "cancelled"
    assert state.values["error_code"] == "CANCELLED"


def test_choose_image_mode_payload_and_manual_branch() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}})
    run(graph, Command(resume={"approved": True}))
    paused = graph.get_state(config())
    payload = paused.interrupts[0].value
    assert payload["default"] == "auto"
    for key in ("characters", "scene_images", "auto_images_usd", "manual_saving_usd"):
        assert key in payload
    visited = run(graph, Command(resume={"mode": "manual"}))
    assert "manual_images" in visited
    assert "character_sheets" not in visited and "review_characters" not in visited
    values = graph.get_state(config()).values
    assert values["options"]["image_mode"] == "manual"
    assert values.get("error_code") != "INVALID_STATE"


def test_choose_image_mode_skipped_when_preset() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}, "options": {"image_mode": "auto"}})
    run(graph, Command(resume={"approved": True}))
    assert graph.get_state(config()).next == ("review_characters",)


def test_cancel_while_choosing_image_mode() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}})
    run(graph, Command(resume={"approved": True}))
    assert graph.get_state(config()).next == ("choose_image_mode",)
    visited = run(graph, Command(resume={"cancel": True}))
    assert "character_sheets" not in visited and "compose_render" not in visited
    state = graph.get_state(config())
    assert state.next == ()
    assert state.values["status"] == "cancelled"
    assert state.values["error_code"] == "CANCELLED"


def test_invalid_image_mode_fails_validation() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}})
    run(graph, Command(resume={"approved": True}))
    run(graph, Command(resume={"mode": "bogus"}))
    assert graph.get_state(config()).values["error_code"] == "VALIDATION_ERROR"


def test_status_reducer_keeps_terminal() -> None:
    assert merge_status("cancelled", "running") == "cancelled"
    assert merge_status("running", "cancelled") == "cancelled"
    assert merge_status("running", "done") == "done"
    assert merge_status(None, "running") == "running"
