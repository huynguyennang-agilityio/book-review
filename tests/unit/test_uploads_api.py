"""POST /projects/{id}/uploads và GET /media cho ảnh tải lên (chọn ảnh manual, ngày 2)."""

import io
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from book_review_api import projects, uploads
from book_review_api.config import Settings, get_settings
from book_review_api.db import user_db
from book_review_api.errors import AppError, ErrorCode, register_error_handlers

OWNER = uuid4()


class FakeGraph:
    async def aget_state(self, _config: Any) -> Any:
        return SimpleNamespace(values={})


def make_image(
    fmt: str = "PNG", size: tuple[int, int] = (720, 1280), mode: str = "RGB", **save: Any
) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, (200, 30, 30)).save(buf, format=fmt, **save)
    return buf.getvalue()


@pytest.fixture
def media(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def client(media: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    (media.parent / "secret.jpg").write_bytes(b"x")
    settings = Settings(media_dir=str(media), _env_file=None)  # type: ignore[call-arg]
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(projects.router)
    app.state.graph = FakeGraph()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[user_db] = lambda: None

    async def load(project_id: UUID, _db: Any) -> projects.Project:
        if project_id != OWNER:  # RLS: project của người khác coi như không tồn tại
            raise AppError(ErrorCode.NOT_FOUND)
        now = datetime.now(UTC)
        return projects.Project(
            id=project_id,
            book_title="x",
            thread_id="t",
            status="awaiting_review",
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(projects, "_load", load)
    with TestClient(app) as c:
        yield c


def post(client: TestClient, data: bytes, pid: UUID = OWNER, name: str = "a.png") -> Any:
    return client.post(f"/projects/{pid}/uploads", files={"file": (name, data, "image/png")})


def test_upload_then_view_via_media(client: TestClient, media: Path) -> None:
    resp = post(client, make_image())
    assert resp.status_code == 201
    body = resp.json()
    assert body["warnings"] == []
    assert body["path"].startswith(f"uploads/{OWNER}/") and body["path"].endswith(".jpg")
    assert (media / body["path"]).is_file()
    got = client.get(f"/projects/{OWNER}/media", params={"path": body["path"]})
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(got.content)) as img:
        assert img.format == "JPEG" and img.size == (720, 1280)


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_accepts_allowed_formats(client: TestClient, fmt: str) -> None:
    assert post(client, make_image(fmt)).status_code == 201


def test_same_image_is_stored_once(client: TestClient, media: Path) -> None:
    data = make_image()
    assert post(client, data).json()["path"] == post(client, data).json()["path"]
    assert len(list((media / "uploads" / str(OWNER)).glob("*.jpg"))) == 1


def test_exif_is_stripped(client: TestClient, media: Path) -> None:
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"
    resp = post(client, make_image("JPEG", exif=exif.tobytes()))
    saved = (media / resp.json()["path"]).read_bytes()
    with Image.open(io.BytesIO(saved)) as img:
        assert not img.getexif()
    assert b"SecretCamera" not in saved


def test_transparent_png_becomes_opaque_jpeg(client: TestClient, media: Path) -> None:
    resp = post(client, make_image("PNG", mode="RGBA"))
    assert resp.status_code == 201
    with Image.open(media / resp.json()["path"]) as img:
        assert img.mode == "RGB"


def test_small_and_wrong_ratio_return_warnings_but_accept(client: TestClient) -> None:
    resp = post(client, make_image(size=(400, 400)))
    assert resp.status_code == 201
    assert {w["code"] for w in resp.json()["warnings"]} == {"LOW_RESOLUTION", "ASPECT_MISMATCH"}


def test_big_image_with_right_ratio_has_no_warning(client: TestClient) -> None:
    assert post(client, make_image(size=(1080, 1920))).json()["warnings"] == []


def test_other_owner_is_404_and_stores_nothing(client: TestClient, media: Path) -> None:
    resp = post(client, make_image(), pid=uuid4())
    assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"
    assert not (media / "uploads").exists()


@pytest.mark.parametrize("data", [b"%PDF-1.4 not an image", b"GIF89a..."])
def test_unsupported_format_is_415(client: TestClient, data: bytes) -> None:
    resp = post(client, data)
    assert resp.status_code == 415 and resp.json()["code"] == "UNSUPPORTED_IMAGE"


def test_gif_is_rejected(client: TestClient) -> None:
    assert post(client, make_image("GIF")).json()["code"] == "UNSUPPORTED_IMAGE"


def test_too_large_is_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uploads, "MAX_BYTES", 1000)
    monkeypatch.setattr(projects, "MAX_BYTES", 1000)
    resp = post(client, make_image(size=(500, 500), mode="RGB"))
    assert resp.status_code == 413 and resp.json()["code"] == "IMAGE_TOO_LARGE"


def test_truncated_image_is_422(client: TestClient) -> None:
    resp = post(client, make_image("PNG", size=(300, 300))[:-200])
    assert resp.status_code == 422 and resp.json()["code"] == "INVALID_IMAGE"


def test_limit_per_project(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(projects, "MAX_PER_PROJECT", 2)
    for color in range(2):
        buf = io.BytesIO()
        Image.new("RGB", (720, 1280), (color * 100, 50, 0)).save(buf, format="PNG")
        assert post(client, buf.getvalue()).status_code == 201
    resp = post(client, make_image())
    assert resp.status_code == 409 and resp.json()["code"] == "UPLOAD_LIMIT"
    # Ảnh đã có thì tải lại vẫn được, không tính thêm.
    buf = io.BytesIO()
    Image.new("RGB", (720, 1280), (0, 50, 0)).save(buf, format="PNG")
    assert post(client, buf.getvalue()).status_code == 201


@pytest.mark.parametrize(
    "path",
    [
        "uploads/../../secret.jpg",
        f"uploads/{OWNER}/../../../secret.jpg",
        f"uploads/{OWNER}/nothere.jpg",
        f"uploads/{uuid4()}/{'a' * 32}.jpg",  # project khác
        f"uploads/{OWNER}/{'a' * 32}.jpg",  # đúng dạng nhưng không có file
        "secret.jpg",
    ],
)
def test_media_blocks_traversal_and_foreign_paths(client: TestClient, path: str) -> None:
    assert client.get(f"/projects/{OWNER}/media", params={"path": path}).status_code == 404


def test_media_does_not_serve_other_projects_upload(client: TestClient, media: Path) -> None:
    other = uuid4()
    name = "b" * 32 + ".jpg"
    (media / "uploads" / str(other)).mkdir(parents=True)
    (media / "uploads" / str(other) / name).write_bytes(make_image("JPEG"))
    path = f"uploads/{other}/{name}"
    assert client.get(f"/projects/{OWNER}/media", params={"path": path}).status_code == 404
