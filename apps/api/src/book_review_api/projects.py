"""REST cho project. Truy vấn qua `UserDB` nên RLS lọc theo người dùng; project của người khác
trả 404 như không tồn tại."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints

from book_review_api.config import Settings, get_settings
from book_review_api.db import UserDB
from book_review_api.errors import AppError, ErrorCode
from book_review_api.graph.nodes.precheck import MAX_AUTHOR_LEN, find_excluded_keyword
from book_review_api.storyboard.rewrite import SceneNotFound

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])

ProjectStatus = Literal[
    "created", "running", "awaiting_review", "done", "failed", "cancelled", "rejected"
]


class ProjectCreate(BaseModel):
    book_title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    # Không lưu vào DB; chỉ kiểm độ dài như tên sách, tác giả đi theo state của graph.
    book_author: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=MAX_AUTHOR_LEN)
    ] = None


class Project(BaseModel):
    id: UUID
    book_title: str
    thread_id: str = Field(description="thread_id của graph book_review cho project này")
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


_COLUMNS = "id, book_title, thread_id, status, created_at, updated_at"


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, db: UserDB) -> Project:
    # Chặn sớm, chưa tạo project. Node `precheck` trong graph vẫn kiểm lại.
    if find_excluded_keyword(body.book_title):
        raise AppError(ErrorCode.GENRE_EXCLUDED)
    # `user_id` lấy mặc định từ auth.uid(), RLS kiểm lại khi insert.
    cur = await db.execute(
        f"insert into public.projects (book_title, thread_id) values (%s, %s) returning {_COLUMNS}",
        [body.book_title, str(uuid4())],
    )
    row = await cur.fetchone()
    assert row is not None
    return Project.model_validate(row)


@router.get("/{project_id}")
async def get_project(project_id: UUID, db: UserDB) -> Project:
    cur = await db.execute(f"select {_COLUMNS} from public.projects where id = %s", [project_id])
    row = await cur.fetchone()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return Project.model_validate(row)


class CancelResult(Project):
    # Chi phí đã tiêu tới lúc huỷ (cộng dồn trong state của graph, không mất khi huỷ).
    cost: dict[str, float] = Field(default_factory=dict)


FINISHED = {"done", "failed", "rejected"}


async def _load(project_id: UUID, db: UserDB) -> Project:
    cur = await db.execute(f"select {_COLUMNS} from public.projects where id = %s", [project_id])
    row = await cur.fetchone()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return Project.model_validate(row)


@router.post("/{project_id}/cancel")
async def cancel_project(project_id: UUID, request: Request, db: UserDB) -> CancelResult:
    """Huỷ project (idempotent). Đặt cờ huỷ ở Redis để node tiếp theo và job của worker dừng, nếu
    graph đang chờ duyệt thì ghi luôn trạng thái `cancelled` vào state. Chi phí đã tiêu vẫn còn."""
    project = await _load(project_id, db)
    if project.status in FINISHED:
        raise AppError(ErrorCode.INVALID_STATE, "Project đã kết thúc, không huỷ được.")
    config: Any = {"configurable": {"thread_id": project.thread_id}}
    graph = request.app.state.graph
    flags = request.app.state.cancel_flags
    try:
        await asyncio.to_thread(flags.set, project.thread_id)
    except Exception:  # noqa: BLE001
        log.exception("không đặt được cờ huỷ ở Redis")
    cost: dict[str, float] = {}
    if project.status != "created":
        snap = await graph.aget_state(config)
        cost = dict(snap.values.get("cost") or {})
        waiting = [t for t in snap.tasks if t.interrupts]
        if project.status == "awaiting_review" and len(waiting) == 1:
            # Graph đang dừng ở điểm duyệt, không có run nào giữ checkpoint: ghi thẳng `cancelled`.
            await graph.aupdate_state(
                config,
                {
                    "cancel_requested": True,
                    "status": "cancelled",
                    "error_code": ErrorCode.CANCELLED.value,
                },
                as_node=waiting[0].name,
            )
    cur = await db.execute(
        "update public.projects set status = 'cancelled', updated_at = now() where id = %s"
        f" returning {_COLUMNS}",
        [project_id],
    )
    row = await cur.fetchone()
    assert row is not None
    return CancelResult(**Project.model_validate(row).model_dump(), cost=cost)


class RewriteRequest(BaseModel):
    instruction: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    # Lời đọc đang nằm trong ô sửa (chưa lưu), để yêu cầu như "ngắn hơn" áp lên bản đang sửa.
    narration_vi: Annotated[str, StringConstraints(max_length=2000)] | None = None


class RewriteResult(BaseModel):
    scene_id: int
    narration_vi: str
    on_screen_text_vi: str | None
    faithfulness: float | None
    unsupported: list[dict[str, str]] = Field(default_factory=list)
    cost_usd: float


@router.post("/{project_id}/scenes/{scene_id}/rewrite")
async def rewrite_scene(
    project_id: UUID, scene_id: int, body: RewriteRequest, request: Request, db: UserDB
) -> RewriteResult:
    """Viết lại một cảnh theo yêu cầu bằng lời. Chỉ trả bản đề xuất; kịch bản chỉ đổi khi người
    dùng bấm Duyệt kèm bản sửa."""
    project = await _load(project_id, db)
    if project.status != "awaiting_review":
        raise AppError(ErrorCode.INVALID_STATE, "Chỉ viết lại được khi đang chờ duyệt kịch bản.")
    rewriter = getattr(request.app.state, "scene_rewriter", None)
    if rewriter is None:
        raise AppError(ErrorCode.PROVIDER_UNAVAILABLE)
    snap = await request.app.state.graph.aget_state(
        {"configurable": {"thread_id": project.thread_id}}
    )
    storyboard = snap.values.get("storyboard")
    if not storyboard:
        raise AppError(ErrorCode.INVALID_STATE, "Chưa có kịch bản để viết lại.")
    try:
        result = await asyncio.to_thread(
            rewriter, storyboard, scene_id, body.instruction, body.narration_vi
        )
    except SceneNotFound:
        raise AppError(ErrorCode.NOT_FOUND, "Không có cảnh này trong kịch bản.") from None
    except Exception:
        log.exception("viết lại cảnh thất bại")
        raise AppError(ErrorCode.PROVIDER_UNAVAILABLE) from None
    return RewriteResult(**result)


@router.get("/{project_id}/media")
async def get_media(
    project_id: UUID,
    path: str,
    request: Request,
    db: UserDB,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    """Ảnh ứng viên nhân vật của project (cho `<img>` trên màn duyệt). Chỉ phục vụ file mà graph
    của chính project này đã tạo (nằm trong `character_candidates`), không đọc đường dẫn tuỳ ý."""
    project = await _load(project_id, db)
    snap = await request.app.state.graph.aget_state(
        {"configurable": {"thread_id": project.thread_id}}
    )
    candidates = snap.values.get("character_candidates") or {}
    allowed = {p for c in candidates.values() for p in c.get("images", [])}
    media_dir = Path(settings.media_dir).resolve()
    file = (media_dir / path).resolve()
    if path not in allowed or not file.is_relative_to(media_dir) or not file.is_file():
        raise AppError(ErrorCode.NOT_FOUND)
    return FileResponse(file, media_type="image/jpeg", headers={"cache-control": "private"})


# Đầu ra tải được: khoá trong `asset_refs` -> (tên file khi tải, nhãn, media type).
OUTPUTS: dict[str, tuple[str, str, str]] = {
    "video:final": ("final_review.mp4", "Video có nhạc nền", "video/mp4"),
    "video:voice_only": ("final_review_voice_only.mp4", "Video chỉ giọng đọc", "video/mp4"),
    "subtitles:srt": ("subtitles.srt", "Phụ đề (.srt)", "application/x-subrip"),
    "subtitles:ass": ("subtitles.ass", "Phụ đề (.ass)", "text/plain; charset=utf-8"),
    "caption": ("caption.txt", "Caption và hashtag", "text/plain; charset=utf-8"),
    "cover": ("cover.jpg", "Ảnh bìa", "image/jpeg"),
    "sources": ("sources.md", "Nguồn và trích dẫn", "text/markdown; charset=utf-8"),
    "project": ("project.json", "Dữ liệu project", "application/json"),
}


class OutputFile(BaseModel):
    key: str
    name: str
    label: str
    size: int


async def _output_refs(project_id: UUID, request: Request, db: UserDB) -> dict[str, str]:
    project = await _load(project_id, db)
    snap = await request.app.state.graph.aget_state(
        {"configurable": {"thread_id": project.thread_id}}
    )
    refs: dict[str, str] = snap.values.get("asset_refs") or {}
    return refs


def _resolve_output(media_dir: str, ref: str) -> Path | None:
    root = Path(media_dir).resolve()
    file = (root / ref).resolve()
    return file if file.is_relative_to(root) and file.is_file() else None


@router.get("/{project_id}/outputs")
async def list_outputs(
    project_id: UUID,
    request: Request,
    db: UserDB,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[OutputFile]:
    """Các file đầu ra của project đã dựng xong (video, voice-only, phụ đề, caption, bìa...)."""
    refs = await _output_refs(project_id, request, db)
    result: list[OutputFile] = []
    for key, (name, label, _type) in OUTPUTS.items():
        file = _resolve_output(settings.media_dir, refs[key]) if key in refs else None
        if file is not None:
            result.append(OutputFile(key=key, name=name, label=label, size=file.stat().st_size))
    return result


@router.get("/{project_id}/outputs/{key}")
async def download_output(
    project_id: UUID,
    key: str,
    request: Request,
    db: UserDB,
    settings: Annotated[Settings, Depends(get_settings)],
    download: bool = False,
) -> FileResponse:
    """Tải một file đầu ra. Chỉ phục vụ khoá trong `OUTPUTS` mà graph của project này đã tạo."""
    refs = await _output_refs(project_id, request, db)
    if key not in OUTPUTS or key not in refs:
        raise AppError(ErrorCode.NOT_FOUND)
    file = _resolve_output(settings.media_dir, refs[key])
    if file is None:
        raise AppError(ErrorCode.NOT_FOUND)
    name, _label, media_type = OUTPUTS[key]
    return FileResponse(
        file,
        media_type=media_type,
        filename=name if download else None,
        headers={"cache-control": "private"},
    )
