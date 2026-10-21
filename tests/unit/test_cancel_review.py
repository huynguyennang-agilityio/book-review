"""Duyệt kịch bản có sửa (ngày 15) và huỷ giữa chừng: cờ huỷ, chi phí giữ lại, worker dừng job."""

import asyncio
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from test_graph import config, run

from book_review_api import queue
from book_review_api.graph.build import build_graph
from book_review_api.graph.nodes.common import Cancelled
from book_review_api.graph.nodes.review import EDITED_FLAG, apply_edits
from book_review_api.queue import ArqJobRunner

STORYBOARD: dict[str, Any] = {
    "book": {"title": "Nhà giả kim"},
    "book_category": "fiction",
    "spoiler_free": True,
    "hook_vi": "",
    "style_prompt_en": "",
    "caption_vi": "",
    "scenes": [
        {
            "id": 1,
            "section": "hook",
            "narration_vi": "Mở đầu.",
            "scene_type": "title",
            "mood": "warm",
            "flags": [],
        },
        {
            "id": 2,
            "section": "body",
            "scene_type": "title",
            "mood": "warm",
            "narration_vi": "Thân bài.",
            "on_screen_text_vi": "Chữ cũ",
            "faithfulness": 0.5,
            "flags": ["LOW_FAITHFULNESS"],
            "citations": [{"source_id": "s", "chunk_id": "c", "quote": "q"}],
        },
    ],
}


def edit(scene_id: int, narration: str, on_screen: str | None = None) -> dict[str, Any]:
    return {"scene_id": scene_id, "narration_vi": narration, "on_screen_text_vi": on_screen}


def test_apply_edits_updates_scene_and_clears_score() -> None:
    out = apply_edits(STORYBOARD, [edit(2, "  Thân bài mới.  ", " ")])
    assert out is not None
    hook, body = out["scenes"]
    assert hook == STORYBOARD["scenes"][0]
    assert body["narration_vi"] == "Thân bài mới."
    assert body["on_screen_text_vi"] is None
    assert body["faithfulness"] is None
    assert body["flags"] == [EDITED_FLAG]
    assert body["citations"] == STORYBOARD["scenes"][1]["citations"]
    # Bản gốc không bị sửa tại chỗ.
    assert STORYBOARD["scenes"][1]["narration_vi"] == "Thân bài."


@pytest.mark.parametrize(
    "edits",
    [
        None,
        "x",
        [edit(9, "a")],
        [edit(1, "  ")],
        [{"scene_id": 1}],
        [{**edit(1, "a"), "on_screen_text_vi": 5}],
    ],
)
def test_apply_edits_rejects_invalid(edits: Any) -> None:
    assert apply_edits(STORYBOARD, edits) is None


def test_review_resume_applies_edits_then_continues() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}, "storyboard": STORYBOARD})
    assert graph.get_state(config()).next == ("review_script",)
    resume = {"approved": True, "edits": [edit(1, "Mở đầu mới.")]}
    visited = run(graph, Command(resume=resume))
    assert "tts_align" in visited
    state = graph.get_state(config())
    assert state.values["storyboard"]["scenes"][0]["narration_vi"] == "Mở đầu mới."
    assert state.values["storyboard"]["scenes"][0]["flags"] == [EDITED_FLAG]
    assert state.next == ("review_characters",)


def test_review_resume_with_invalid_edits_fails_before_media() -> None:
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}, "storyboard": STORYBOARD})
    visited = run(graph, Command(resume={"approved": True, "edits": [edit(7, "x")]}))
    assert "tts_align" not in visited
    state = graph.get_state(config())
    assert state.values["status"] == "failed"
    assert state.values["error_code"] == "VALIDATION_ERROR"


class FlagsAfter:
    """Cờ huỷ bật sau `calls` lần kiểm tra (mỗi node kiểm một lần)."""

    def __init__(self, calls: int) -> None:
        self.calls = calls
        self.seen: list[str] = []

    def set(self, thread_id: str) -> None:
        self.calls = 0

    def is_set(self, thread_id: str) -> bool:
        self.seen.append(thread_id)
        self.calls -= 1
        return self.calls < 0


def test_redis_flag_stops_next_nodes_and_keeps_cost() -> None:
    # 6 node tới review_script + 1 lần node đó chạy lại khi resume; sau đó tts/ảnh bị huỷ.
    flags = FlagsAfter(7)
    graph = build_graph(InMemorySaver(), cancel_flags=flags)
    run(graph, {"book": {"title": "Nhà giả kim"}, "cost": {"usd": 0.25}})
    assert graph.get_state(config()).next == ("review_script",)
    visited = run(graph, Command(resume={"approved": True}))
    assert "tts_align" not in visited
    assert "compose_render" not in visited
    state = graph.get_state(config())
    assert state.next == ()
    assert state.values["status"] == "cancelled"
    assert state.values["error_code"] == "CANCELLED"
    assert state.values["cost"] == {"usd": 0.25}
    assert set(flags.seen) == {"t1"}


def test_flag_set_while_waiting_cancels_on_resume() -> None:
    flags = FlagsAfter(10**6)
    graph = build_graph(InMemorySaver(), cancel_flags=flags)
    run(graph, {"book": {"title": "Nhà giả kim"}})
    flags.set("t1")
    assert run(graph, Command(resume={"approved": True})) == ["review_script"]
    assert graph.get_state(config()).values["status"] == "cancelled"


def test_update_state_as_interrupted_node_ends_graph() -> None:
    """Cách endpoint huỷ ghi `cancelled` khi graph đang chờ duyệt."""
    graph = build_graph(InMemorySaver())
    run(graph, {"book": {"title": "Nhà giả kim"}, "cost": {"usd": 0.1}})
    snap = graph.get_state(config())
    [waiting] = [t for t in snap.tasks if t.interrupts]
    graph.update_state(
        config(),
        {"cancel_requested": True, "status": "cancelled", "error_code": "CANCELLED"},
        as_node=waiting.name,
    )
    state = graph.get_state(config())
    assert state.next == ()
    assert state.values["status"] == "cancelled"
    assert state.values["cost"] == {"usd": 0.1}


class FakeJob:
    def __init__(self) -> None:
        self.aborted = False

    async def result(self, timeout: float, poll_delay: float) -> Any:
        await asyncio.sleep(0.01)
        raise TimeoutError

    async def abort(self, timeout: float) -> bool:
        self.aborted = True
        return True


class FakePool:
    def __init__(self, job: FakeJob) -> None:
        self.job = job
        self.closed = False

    async def enqueue_job(self, function: str, payload: dict[str, Any]) -> FakeJob:
        return self.job

    async def aclose(self) -> None:
        self.closed = True


def make_runner(monkeypatch: pytest.MonkeyPatch, job: FakeJob, flags: Any, timeout_s: float = 600):  # type: ignore[no-untyped-def]
    pool = FakePool(job)

    async def fake_create_pool(settings: Any) -> FakePool:
        return pool

    monkeypatch.setattr(queue, "create_pool", fake_create_pool)
    return ArqJobRunner("redis://x", timeout_s, flags), pool


def test_job_runner_aborts_job_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    job = FakeJob()
    runner, pool = make_runner(monkeypatch, job, FlagsAfter(2))
    with pytest.raises(Cancelled):
        asyncio.run(runner._run("tts", {}, "t1"))
    assert job.aborted
    assert pool.closed


def test_job_runner_times_out_without_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    job = FakeJob()
    runner, _ = make_runner(monkeypatch, job, None, timeout_s=0.05)
    with pytest.raises(queue.JobFailed):
        asyncio.run(runner._run("tts", {}, "t1"))
    assert job.aborted


def test_review_payload_has_source_links() -> None:
    lookup_calls: list[list[str]] = []

    def lookup(chunk_ids: Any) -> dict[str, dict[str, Any]]:
        lookup_calls.append(list(chunk_ids))
        return {"s": {"url": "https://vi.wikipedia.org/wiki/x", "title": "Wiki"}}

    graph = build_graph(InMemorySaver(), source_lookup=lookup)
    run(graph, {"book": {"title": "Nhà giả kim"}, "storyboard": STORYBOARD})
    payload = graph.get_state(config()).interrupts[0].value
    assert lookup_calls == [["c"]]
    assert payload["sources"] == [
        {
            "source_id": "s",
            "scene_ids": [2],
            "url": "https://vi.wikipedia.org/wiki/x",
            "title": "Wiki",
        }
    ]
