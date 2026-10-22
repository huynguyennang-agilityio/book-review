"""GET /projects/{id}/outputs: chỉ phục vụ file nằm trong asset_refs của project (ngày 19)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from book_review_api import projects
from book_review_api.config import Settings, get_settings
from book_review_api.db import user_db
from book_review_api.errors import register_error_handlers


class FakeGraph:
    def __init__(self, refs: dict[str, str]) -> None:
        self.refs = refs

    async def aget_state(self, _config: Any) -> Any:
        return SimpleNamespace(values={"asset_refs": self.refs})


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    (tmp_path / "render").mkdir()
    (tmp_path / "render" / "v.mp4").write_bytes(b"video")
    (tmp_path / "render" / "c.txt").write_text("cap", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("x", encoding="utf-8")
    settings = Settings(media_dir=str(tmp_path), _env_file=None)  # type: ignore[call-arg]
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(projects.router)
    app.state.graph = FakeGraph(
        {
            "video:final": "render/v.mp4",
            "caption": "render/c.txt",
            "sources": "../secret.txt",  # ngoài media_dir: phải bị chặn
            "subtitles:srt": "render/missing.srt",
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[user_db] = lambda: None

    async def load(project_id: Any, _db: Any) -> projects.Project:
        now = datetime.now(UTC)
        return projects.Project(
            id=uuid4(), book_title="x", thread_id="t", status="done", created_at=now, updated_at=now
        )

    monkeypatch.setattr(projects, "_load", load)
    with TestClient(app) as c:
        yield c


def test_lists_only_existing_files_inside_media_dir(client: TestClient) -> None:
    resp = client.get(f"/projects/{uuid4()}/outputs")
    assert resp.status_code == 200
    assert [o["key"] for o in resp.json()] == ["video:final", "caption"]


def test_download_sets_filename_only_when_asked(client: TestClient) -> None:
    pid = uuid4()
    inline = client.get(f"/projects/{pid}/outputs/video:final")
    assert inline.content == b"video" and "attachment" not in inline.headers.get(
        "content-disposition", ""
    )
    attach = client.get(f"/projects/{pid}/outputs/video:final?download=true")
    assert 'filename="final_review.mp4"' in attach.headers["content-disposition"]


@pytest.mark.parametrize("key", ["sources", "subtitles:srt", "cover", "video:raw", "../x"])
def test_unavailable_output_is_404(client: TestClient, key: str) -> None:
    assert client.get(f"/projects/{uuid4()}/outputs/{key}").status_code == 404
