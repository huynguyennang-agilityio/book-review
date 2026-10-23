"""Chạy lại project lỗi: tạo checkpoint mới từ bước trước khi lỗi, kể cả khi bước đó có
nhiều node chạy song song."""

import asyncio
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from book_review_api.agui import _rewind_failed


class State(TypedDict, total=False):
    status: str
    left: str
    right: str
    done: bool


def make_graph(fail_times: list[int]) -> Any:
    def start(state: State) -> State:
        return {"status": "running"}

    def left(state: State) -> State:
        return {"left": "x"}

    def right(state: State) -> State:
        return {"right": "y"}

    def finish(state: State) -> State:
        if fail_times[0] > 0:
            fail_times[0] -= 1
            return {"status": "failed"}
        return {"status": "done", "done": True}

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


def test_rewind_after_parallel_step_reruns_only_failed_node() -> None:
    async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
        graph = make_graph([1])
        config: RunnableConfig = {"configurable": {"thread_id": "t"}}
        first = await graph.ainvoke({}, config)
        await _rewind_failed(graph, "t")
        again = await graph.ainvoke(None, config)
        return first, again

    first, again = asyncio.run(scenario())
    assert first["status"] == "failed"
    assert again["status"] == "done"
    assert again["done"] is True
    assert (again["left"], again["right"]) == ("x", "y")
