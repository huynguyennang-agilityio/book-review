"""POST /agent (AG-UI) với Postgres thật và graph khung: cần JWT, chỉ chạy được project của mình."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_projects_api import client, create, token  # noqa: F401

from book_review_api.graph.build import build_graph
from book_review_api.graph.state import BookInput


def run_body(thread_id: str, title: str = "Nhà giả kim") -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": "run-1",
        "state": {"book": {"title": title}},
        "messages": [{"id": "m1", "role": "user", "content": title}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def events(text: str) -> list[dict[str, Any]]:
    return [json.loads(line[5:]) for line in text.splitlines() if line.startswith("data:")]


def test_requires_jwt(client: TestClient) -> None:  # noqa: F811
    resp = client.post("/agent", json=run_body("x"))
    assert resp.status_code == 401


def test_other_users_thread_is_404(client: TestClient, make_user: Callable[[str], str]) -> None:  # noqa: F811
    a, b = make_user("a@example.com"), make_user("b@example.com")
    thread_id = create(client, a).json()["thread_id"]
    resp = client.post("/agent", json=run_body(thread_id), headers=token(b))
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_run_streams_steps_interrupt_and_updates_status(
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
) -> None:
    a = make_user("a@example.com")
    project = create(client, a).json()
    resp = client.post("/agent", json=run_body(project["thread_id"]), headers=token(a))
    assert resp.status_code == 200
    evs = events(resp.text)
    types = [e["type"] for e in evs]
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_FINISHED"
    steps = [e["stepName"] for e in evs if e["type"] == "STEP_STARTED"]
    assert steps[0] == "precheck"
    nodes = [
        (e["value"]["node"], e["value"]["phase"])
        for e in evs
        if e["type"] == "CUSTOM" and e["name"] == "node"
    ]
    assert nodes[:2] == [("precheck", "start"), ("precheck", "end")]
    # Graph khung dừng ở điểm duyệt kịch bản.
    assert "review_script" in steps
    assert evs[-1]["outcome"]["type"] == "interrupt"
    got = client.get(f"/projects/{project['id']}", headers=token(a)).json()
    assert got["status"] == "awaiting_review"


CANDIDATES = [
    {"title": "Sức mạnh của thói quen", "author": "Charles Duhigg"},
    {"title": "Sức mạnh của hiện tại", "author": "Eckhart Tolle"},
]


@pytest.fixture
def ambiguous_research(monkeypatch: pytest.MonkeyPatch) -> None:
    """Research agent giả trả hai ứng viên để graph dừng ở `identify_confirm`."""

    def research(book: BookInput) -> dict[str, Any]:
        return {
            "research": {"book": CANDIDATES[0], "candidates": CANDIDATES, "kind": "non_fiction"}
        }

    monkeypatch.setattr(
        "book_review_api.main.build_graph",
        lambda **kw: build_graph(**kw, research_runner=research),
    )


def test_identify_confirm_interrupt_and_resume(
    ambiguous_research: None,
    client: TestClient,  # noqa: F811
    make_user: Callable[[str], str],
) -> None:
    a = make_user("a@example.com")
    project = create(client, a, "Sức mạnh").json()
    body = run_body(project["thread_id"], "Sức mạnh")
    first = events(client.post("/agent", json=body, headers=token(a)).text)
    outcome = first[-1]["outcome"]
    assert outcome["type"] == "interrupt"
    interrupt = outcome["interrupts"][0]
    raw = interrupt["metadata"]["langgraph"]["raw"]
    assert raw["type"] == "identify_confirm"
    assert raw["candidates"] == CANDIDATES

    resume = [{"interruptId": interrupt["id"], "status": "resolved", "payload": {"index": 1}}]
    second = events(
        client.post(
            "/agent",
            json={**body, "runId": "run-2", "messages": [], "resume": resume},
            headers=token(a),
        ).text
    )
    last = second[-1]["outcome"]
    assert last["type"] == "interrupt"
    assert last["interrupts"][0]["metadata"]["langgraph"]["raw"]["type"] == "review_script"
    got = client.get(f"/projects/{project['id']}", headers=token(a)).json()
    assert got["status"] == "awaiting_review"
