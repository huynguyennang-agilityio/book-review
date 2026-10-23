"""Chạy lại project lỗi: tạo checkpoint mới từ bước trước khi lỗi, kể cả khi bước đó có
nhiều node chạy song song; có thể kèm ngân sách mới, và giữ chi phí đã tiêu trong lần lỗi."""

import asyncio
from typing import Annotated, Any, TypedDict

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from book_review_api.agui import _rewind_failed
from book_review_api.errors import AppError, ErrorCode
from book_review_api.graph import build
from book_review_api.graph.nodes.common import NodeUpdate, node
from book_review_api.graph.state import BookReviewState, add_costs

CONFIG: RunnableConfig = {"configurable": {"thread_id": "t"}}


class State(TypedDict, total=False):
    status: str
    options: dict[str, Any]
    cost: Annotated[dict[str, float], add_costs]
    left: str
    right: str
    done: bool


def make_graph() -> Any:
    """start → (left ‖ right) → finish; finish lỗi ngân sách khi budget < 2."""

    def start(state: State) -> State:
        return {"status": "running", "cost": {"usd": 0.1}}

    def left(state: State) -> State:
        return {"left": "x", "cost": {"usd": 0.2}}

    def right(state: State) -> State:
        return {"right": "y"}

    def finish(state: State) -> State:
        if (state.get("options") or {}).get("budget_usd", 0) < 2:
            return {"status": "failed", "cost": {"usd": 0.5}}
        return {"status": "done", "done": True, "cost": {"usd": 0.3}}

    g = StateGraph(State)
    g.add_node("start", start)
    g.add_node("left", left)
    g.add_node("right", right)
    g.add_node("finish", finish)
    g.add_edge(START, "start")
    g.add_edge("start", "left")
    g.add_edge("start", "right")
    g.add_edge(["left", "right"], "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=InMemorySaver())


def rerun(graph: Any, budget: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
        first = await graph.ainvoke({"options": {"budget_usd": 1, "voice": "v"}}, CONFIG)
        await _rewind_failed(graph, "t", budget)
        return first, await graph.ainvoke(None, CONFIG)

    return asyncio.run(scenario())


def test_rewind_after_parallel_step_with_new_budget() -> None:
    first, again = rerun(make_graph(), 3)
    assert first["status"] == "failed"
    assert again["status"] == "done"
    assert (again["left"], again["right"]) == ("x", "y")
    assert again["options"] == {"budget_usd": 3.0, "voice": "v"}
    # 0,8 của lần lỗi (gồm 0,5 node lỗi đã tiêu) + 0,3 lần chạy lại.
    assert again["cost"]["usd"] == pytest.approx(1.1)


def test_rewind_without_budget_keeps_cost_and_options() -> None:
    first, again = rerun(make_graph(), None)
    assert again["status"] == "failed"  # ngân sách cũ vẫn thiếu
    assert again["options"]["budget_usd"] == 1
    assert again["cost"]["usd"] == pytest.approx(first["cost"]["usd"] + 0.5)


@pytest.mark.parametrize("budget", [0.5, 0.8, 21, "3", True])
def test_invalid_budget_is_rejected(budget: Any) -> None:
    graph = make_graph()

    async def scenario() -> None:
        await graph.ainvoke({"options": {"budget_usd": 1}}, CONFIG)
        await _rewind_failed(graph, "t", budget)

    with pytest.raises(AppError) as err:
        asyncio.run(scenario())
    assert err.value.code == ErrorCode.VALIDATION_ERROR


def test_skeleton_graph_scene_images_over_budget_then_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph thật: `scene_images` dừng vì ngân sách sau bước song song (subtitles,
    review_characters); tăng ngân sách rồi chạy tiếp tới `done`."""

    calls: list[float] = []

    @node
    def scene_images(state: BookReviewState) -> NodeUpdate:
        budget = float(state["options"]["budget_usd"])
        calls.append(budget)
        if budget < 2:
            return {"status": "failed", "error_code": "BUDGET_EXCEEDED", "cost": {"usd": 0.9}}
        return {"cost": {"usd": 0.5}}

    monkeypatch.setitem(build.NODES, "scene_images", scene_images)
    graph: Any = build.build_graph(InMemorySaver())
    start = {
        "book": {"title": "Nhà giả kim"},
        "options": {"image_mode": "auto", "budget_usd": 1},
    }

    async def scenario() -> dict[str, Any]:
        await graph.ainvoke(start, CONFIG)
        await graph.ainvoke(Command(resume={"approved": True}), CONFIG)  # duyệt kịch bản
        failed = await graph.ainvoke(Command(resume={"approved": True}), CONFIG)  # nhân vật
        assert failed["status"] == "failed"
        assert failed["error_code"] == "BUDGET_EXCEEDED"
        await _rewind_failed(graph, "t", 2.5)
        snap = await graph.aget_state(CONFIG)
        assert snap.next == ("scene_images",)
        done: dict[str, Any] = await graph.ainvoke(None, CONFIG)
        return done

    done = asyncio.run(scenario())
    assert done["status"] == "done"
    assert calls == [1, 2.5]
    assert done["options"]["budget_usd"] == 2.5
    assert done["cost"]["usd"] == pytest.approx(1.4)
