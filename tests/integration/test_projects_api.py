"""POST/GET /projects qua HTTP với Postgres thật: RLS chặn đọc project của người khác."""

import time
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from book_review_api.auth import get_jwks_client
from book_review_api.config import Settings, get_settings
from book_review_api.main import app

SECRET = "test-secret-at-least-32-bytes-long-xxxxxxxx"


def token(user_id: str) -> dict[str, str]:
    now = int(time.time())
    claims = {"sub": user_id, "aud": "authenticated", "role": "authenticated", "exp": now + 600}
    return {"Authorization": f"Bearer {jwt.encode(claims, SECRET, algorithm='HS256')}"}


@pytest.fixture
def client(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = Settings(database_url=database_url, supabase_jwt_secret=SECRET, _env_file=None)  # type: ignore[call-arg]
    # lifespan đọc get_settings() trực tiếp, route đọc qua Depends.
    monkeypatch.setattr("book_review_api.main.get_settings", lambda: settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jwks_client] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def create(client: TestClient, user_id: str, title: str = "Nhà giả kim") -> Any:
    return client.post("/projects", json={"book_title": title}, headers=token(user_id))


def test_create_and_get(client: TestClient, make_user: Callable[[str], str]) -> None:
    a = make_user("a@example.com")
    resp = create(client, a, "  Nhà giả kim  ")
    assert resp.status_code == 201
    project = resp.json()
    assert project["book_title"] == "Nhà giả kim"
    assert project["status"] == "created"
    assert project["thread_id"]

    got = client.get(f"/projects/{project['id']}", headers=token(a))
    assert got.status_code == 200
    assert got.json() == project


def test_other_user_gets_404(client: TestClient, make_user: Callable[[str], str]) -> None:
    a, b = make_user("a@example.com"), make_user("b@example.com")
    project_id = create(client, a).json()["id"]
    resp = client.get(f"/projects/{project_id}", headers=token(b))
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_excluded_genre_rejected(client: TestClient, make_user: Callable[[str], str]) -> None:
    resp = create(client, make_user("a@example.com"), "Tuyển tập kiếm hiệp")
    assert resp.status_code == 422
    assert resp.json()["code"] == "GENRE_EXCLUDED"


@pytest.mark.parametrize("body", [{}, {"book_title": "   "}, {"book_title": "x" * 201}])
def test_invalid_body(
    client: TestClient, make_user: Callable[[str], str], body: dict[str, Any]
) -> None:
    resp = client.post("/projects", json=body, headers=token(make_user("a@example.com")))
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_requires_auth(client: TestClient) -> None:
    assert client.post("/projects", json={"book_title": "x"}).status_code == 401
    assert client.get(f"/projects/{'0' * 8}-0000-0000-0000-{'0' * 12}").status_code == 401
