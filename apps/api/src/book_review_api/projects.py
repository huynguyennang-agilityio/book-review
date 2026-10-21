"""REST cho project. Truy vấn qua `UserDB` nên RLS lọc theo người dùng; project của người khác
trả 404 như không tồn tại."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints

from book_review_api.db import UserDB
from book_review_api.errors import AppError, ErrorCode
from book_review_api.graph.nodes.precheck import find_excluded_keyword

router = APIRouter(prefix="/projects", tags=["projects"])

ProjectStatus = Literal[
    "created", "running", "awaiting_review", "done", "failed", "cancelled", "rejected"
]


class ProjectCreate(BaseModel):
    book_title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


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
