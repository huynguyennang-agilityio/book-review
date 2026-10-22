"""Huỷ project và duyệt kịch bản qua HTTP với Postgres thật (ngày 15)."""

from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_agent_api import events, run_body
from test_projects_api import client, create, token  # noqa: F401

from book_review_api.main import app


def scene(scene_id: int, section: str, narration: str) -> dict[str, Any]:
    return {
        "id": scene_id,
        "section": section,
        "narration_vi": narration,
        "scene_type": "title",
        "mood": "warm",
    }


STORYBOARD: dict[str, Any] = {
    "book": {"title": "Nhà giả kim"},
    "book_category": "fiction",
    "spoiler_free": True,
    "hook_vi": "",
    "style_prompt_en": "",
    "caption_vi": "",
    "scenes": [scene(1, "hook", "Mở đầu."), scene(2, "body", "Thân bài.")],
}


class MemoryFlags:
    def __init__(self, _url: str = "") -> None:
        self.threads: set[str] = set()

    def set(self, thread_id: str) -> None:
        self.threads.add(thread_id)

    def is_set(self, thread_id: str) -> bool:
        return thread_id in self.threads


@pytest.fixture(autouse=True)
def memory_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("book_review_api.main.RedisCancelFlags", MemoryFlags)


def start_review(client: TestClient, user: str, with_storyboard: bool = True) -> dict[str, Any]:  # noqa: F811
    project: dict[str, Any] = create(client, user).json()
    body = run_body(project["thread_id"])
    if with_storyboard:
        body["state"]["storyboard"] = STORYBOARD
        body["state"]["cost"] = {"usd": 0.2}
    resp = client.post("/agent", json=body, headers=token(user))
    assert events(resp.text)[-1]["outcome"]["type"] == "interrupt"
    return project


def thread_state(thread_id: str) -> Any:
    import asyncio

    return asyncio.run(app.state.graph.aget_state({"configurable": {"thread_id": thread_id}}))


def test_cancel_before_start(client: TestClient, make_user: Callable[[str], str]) -> None:  # noqa: F811
    a = make_user("a@example.com")
    project = create(client, a).json()
    resp = client.post(f"/projects/{project['id']}/cancel", headers=token(a))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert project["thread_id"] in app.state.cancel_flags.threads
    # Project đã huỷ thì không chạy lại được.
    again = client.post("/agent", json=run_body(project["thread_id"]), headers=token(a))
    assert again.status_code == 409
    assert again.json()["code"] == "CANCELLED"


def test_cancel_while_awaiting_review_keeps_cost(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
) -> None:
    a = make_user("a@example.com")
    project = start_review(client, a)
    got = client.get(f"/projects/{project['id']}", headers=token(a)).json()
    assert got["status"] == "awaiting_review"

    resp = client.post(f"/projects/{project['id']}/cancel", headers=token(a))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["cost"] == {"usd": 0.2}
    state = thread_state(project["thread_id"])
    assert state.next == ()
    assert state.values["status"] == "cancelled"
    assert state.values["error_code"] == "CANCELLED"
    assert state.values["cost"] == {"usd": 0.2}
    # Gọi lại vẫn ổn (idempotent) và trạng thái không đổi.
    again = client.post(f"/projects/{project['id']}/cancel", headers=token(a))
    assert again.status_code == 200
    assert again.json()["status"] == "cancelled"


def test_cancel_finished_project_is_rejected(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
    database_url: str,
) -> None:
    a = make_user("a@example.com")
    project = create(client, a).json()
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("update public.projects set status = 'done' where id = %s", [project["id"]])
    resp = client.post(f"/projects/{project['id']}/cancel", headers=token(a))
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE"


def test_cancel_other_users_project_is_404(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
) -> None:
    a, b = make_user("a@example.com"), make_user("b@example.com")
    project = create(client, a).json()
    resp = client.post(f"/projects/{project['id']}/cancel", headers=token(b))
    assert resp.status_code == 404
    assert project["thread_id"] not in app.state.cancel_flags.threads


def test_approve_with_edits_continues_graph(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
) -> None:
    a = make_user("a@example.com")
    project = start_review(client, a)
    first = thread_state(project["thread_id"])
    interrupt_id = first.tasks[0].interrupts[0].id
    resume = [
        {
            "interruptId": interrupt_id,
            "status": "resolved",
            "payload": {
                "approved": True,
                "edits": [
                    {"scene_id": 1, "narration_vi": "Mở đầu đã sửa.", "on_screen_text_vi": None}
                ],
            },
        }
    ]
    body = {**run_body(project["thread_id"]), "runId": "run-2", "messages": [], "resume": resume}
    resp = client.post("/agent", json=body, headers=token(a))
    assert resp.status_code == 200
    last = events(resp.text)[-1]["outcome"]
    assert last["interrupts"][0]["metadata"]["langgraph"]["raw"]["type"] == "choose_image_mode"
    state = thread_state(project["thread_id"])
    assert state.values["storyboard"]["scenes"][0]["narration_vi"] == "Mở đầu đã sửa."
    assert state.values["storyboard"]["scenes"][0]["flags"] == ["EDITED"]


@pytest.fixture
def rewriter() -> Iterator[list[tuple[Any, ...]]]:
    calls: list[tuple[Any, ...]] = []

    def fake(
        storyboard: dict[str, Any], scene_id: int, instruction: str, narration: str | None
    ) -> dict[str, Any]:
        calls.append((scene_id, instruction, narration))
        return {
            "scene_id": scene_id,
            "narration_vi": "Bản viết lại.",
            "on_screen_text_vi": None,
            "faithfulness": 0.95,
            "cost_usd": 0.001,
        }

    app.state.scene_rewriter = fake
    yield calls


def test_rewrite_scene_returns_proposal_without_changing_state(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
    rewriter: list[tuple[Any, ...]],
) -> None:
    a = make_user("a@example.com")
    project = start_review(client, a)
    resp = client.post(
        f"/projects/{project['id']}/scenes/2/rewrite",
        json={"instruction": "ngắn hơn", "narration_vi": "Bản đang sửa"},
        headers=token(a),
    )
    assert resp.status_code == 200
    assert resp.json()["narration_vi"] == "Bản viết lại."
    assert resp.json()["faithfulness"] == 0.95
    assert rewriter == [(2, "ngắn hơn", "Bản đang sửa")]
    state = thread_state(project["thread_id"])
    assert state.values["storyboard"]["scenes"][1]["narration_vi"] == "Thân bài."


def test_rewrite_requires_review_state_and_user(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
    rewriter: list[tuple[Any, ...]],
) -> None:
    a, b = make_user("a@example.com"), make_user("b@example.com")
    created = create(client, a).json()
    url = f"/projects/{created['id']}/scenes/1/rewrite"
    not_ready = client.post(url, json={"instruction": "x"}, headers=token(a))
    assert not_ready.status_code == 409
    assert not_ready.json()["code"] == "INVALID_STATE"
    assert client.post(url, json={"instruction": "x"}, headers=token(b)).status_code == 404
    assert client.post(url, json={"instruction": " "}, headers=token(a)).status_code == 422
    assert rewriter == []


def test_rewrite_without_llm_is_unavailable(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
) -> None:
    a = make_user("a@example.com")
    project = start_review(client, a)
    app.state.scene_rewriter = None
    resp = client.post(
        f"/projects/{project['id']}/scenes/1/rewrite", json={"instruction": "x"}, headers=token(a)
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "PROVIDER_UNAVAILABLE"


def test_media_serves_only_candidate_images(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
    tmp_path: Any,
) -> None:
    from book_review_api.config import Settings, get_settings

    a, b = make_user("a@example.com"), make_user("b@example.com")
    settings: Settings = app.dependency_overrides[get_settings]()
    settings = settings.model_copy(update={"media_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "a_0.jpg").write_bytes(b"jpg")
    (tmp_path / "secret.txt").write_text("x")
    project = create(client, a).json()
    body = run_body(project["thread_id"])
    body["state"]["storyboard"] = STORYBOARD
    body["state"]["character_candidates"] = {"a": {"name": "A", "images": ["characters/a_0.jpg"]}}
    client.post("/agent", json=body, headers=token(a))

    url = f"/projects/{project['id']}/media"
    ok = client.get(url, params={"path": "characters/a_0.jpg"}, headers=token(a))
    assert ok.status_code == 200 and ok.content == b"jpg"
    assert ok.headers["content-type"] == "image/jpeg"
    for bad in ["secret.txt", "../secret.txt", "characters/../secret.txt"]:
        assert client.get(url, params={"path": bad}, headers=token(a)).status_code == 404
    assert (
        client.get(url, params={"path": "characters/a_0.jpg"}, headers=token(b)).status_code == 404
    )
