"""Bộ nhớ dài hạn theo người dùng trên LangGraph Store (ngày 20).

Namespace (mọi thứ nằm dưới `("users", user_id)`):
- `preferences` / `default`: sở thích (giọng đọc, độ dài, tránh spoil...), lần chạy sau tự áp dụng.
- `books` / slug tên sách: lịch sử sách đã làm.
- `characters` / slug: nhân vật đã duyệt.
- `feedback` / thread_id: phản hồi ở các điểm duyệt (ghi chú tạo lại ảnh, sửa tay kịch bản).

Hàm ở đây đồng bộ (dùng trong node). API async gọi qua `asyncio.to_thread` hoặc `a*` của Store.
"""

import logging
from collections.abc import Mapping
from typing import Any

from langgraph.store.base import BaseStore

log = logging.getLogger(__name__)

SECTIONS = ("preferences", "books", "characters", "feedback")

DEFAULT_PREFERENCES: dict[str, Any] = {
    "voice": "default",
    "image_style": "default",
    "length_minutes": 3,
    "no_spoiler": True,
    "tone": "neutral",
}

# Tuỳ chọn của run -> khoá sở thích.
_OPTION_TO_PREF = {"voice": "voice", "minutes": "length_minutes", "no_spoiler": "no_spoiler"}
_MAX_BOOKS = 50


def namespace(user_id: str, section: str) -> tuple[str, ...]:
    return ("users", user_id, section)


def load_preferences(store: BaseStore, user_id: str) -> dict[str, Any]:
    """Sở thích đã lưu (rỗng nếu chưa có). Chỉ trả các khoá hợp lệ."""
    item = store.get(namespace(user_id, "preferences"), "default")
    if item is None:
        return {}
    return {k: v for k, v in item.value.items() if k in DEFAULT_PREFERENCES}


def save_preferences(store: BaseStore, user_id: str, prefs: Mapping[str, Any]) -> dict[str, Any]:
    merged = {
        **load_preferences(store, user_id),
        **{k: prefs[k] for k in prefs if k in DEFAULT_PREFERENCES},
    }
    store.put(namespace(user_id, "preferences"), "default", merged)
    return merged


def apply_preferences(options: Mapping[str, Any], prefs: Mapping[str, Any]) -> dict[str, Any]:
    """Điền sở thích đã lưu vào các tuỳ chọn run còn thiếu. Giá trị người dùng đã chọn thắng."""
    out = dict(options)
    for opt, pref in _OPTION_TO_PREF.items():
        if opt not in out and pref in prefs and prefs[pref] != "default":
            out[opt] = prefs[pref]
    return out


def preferences_from_options(options: Mapping[str, Any]) -> dict[str, Any]:
    return {pref: options[opt] for opt, pref in _OPTION_TO_PREF.items() if opt in options}


def record_run(
    store: BaseStore,
    user_id: str,
    *,
    thread_id: str,
    book: Mapping[str, Any],
    options: Mapping[str, Any],
    characters: Mapping[str, Any],
    feedback: list[dict[str, Any]],
) -> None:
    """Ghi cuối run: sở thích từ tuỳ chọn, lịch sử sách, nhân vật đã duyệt, phản hồi."""
    if prefs := preferences_from_options(options):
        save_preferences(store, user_id, prefs)
    from book_review_api.graph.nodes.characters import slugify  # tránh import vòng

    title = str(book.get("title") or "")
    if title:
        store.put(
            namespace(user_id, "books"),
            # Cùng tên khác tác giả là hai sách khác nhau.
            slugify(f"{title} {book.get('author') or ''}")[:80] or "book",
            {"title": title, "author": book.get("author"), "thread_id": thread_id},
        )
    for slug, value in characters.items():
        store.put(
            namespace(user_id, "characters"),
            slug,
            {"name": value.get("name", slug), "book": title or None},
        )
    if feedback:
        store.put(namespace(user_id, "feedback"), thread_id, {"book": title, "items": feedback})


def export_memory(store: BaseStore, user_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "preferences": {**DEFAULT_PREFERENCES, **load_preferences(store, user_id)}
    }
    for section in SECTIONS[1:]:
        items = store.search(namespace(user_id, section), limit=_MAX_BOOKS)
        out[section] = [{"key": i.key, **i.value} for i in items]
    return out


def delete_memory(store: BaseStore, user_id: str) -> int:
    """Xoá toàn bộ bộ nhớ của người dùng; trả số mục đã xoá."""
    removed = 0
    for section in SECTIONS:
        ns = namespace(user_id, section)
        for item in store.search(ns, limit=1000):
            store.delete(ns, item.key)
            removed += 1
    return removed
