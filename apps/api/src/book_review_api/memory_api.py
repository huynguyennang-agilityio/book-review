"""REST bộ nhớ dài hạn của người dùng (ngày 20): xem, sửa sở thích, xoá hết."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from langgraph.store.base import BaseStore
from pydantic import BaseModel

from book_review_api.auth import CurrentUser, current_user
from book_review_api.memory.store import delete_memory, export_memory, save_preferences

router = APIRouter(prefix="/me/memory", tags=["memory"])


class PreferencesUpdate(BaseModel):
    voice: str | None = None
    length_minutes: int | None = None
    no_spoiler: bool | None = None
    tone: str | None = None
    image_style: str | None = None


def _store(request: Request) -> BaseStore:
    store: BaseStore = request.app.state.store
    return store


@router.get("")
async def get_memory(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> dict[str, Any]:
    return await asyncio.to_thread(export_memory, _store(request), user.user_id)


@router.put("/preferences")
async def put_preferences(
    body: PreferencesUpdate,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> dict[str, Any]:
    prefs = body.model_dump(exclude_none=True)
    await asyncio.to_thread(save_preferences, _store(request), user.user_id, prefs)
    return await asyncio.to_thread(export_memory, _store(request), user.user_id)


@router.delete("")
async def delete_all_memory(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> dict[str, int]:
    removed = await asyncio.to_thread(delete_memory, _store(request), user.user_id)
    return {"deleted": removed}
