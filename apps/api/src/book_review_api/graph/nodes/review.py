"""Điểm dừng chờ người dùng duyệt (interrupt). Giao diện duyệt làm ở ngày 15.

Giá trị resume là dict. `review_script`: `{"approved": true, "edits": [{"scene_id", "narration_vi",
"on_screen_text_vi"}]}` (edits tuỳ chọn, sửa tay từng cảnh trước khi duyệt). `{"cancel": true}` huỷ
luôn project từ màn hình duyệt. Huỷ bằng
`update_state` không dùng được khi hai nhánh song song cùng đang chờ (LangGraph báo
"Ambiguous update"), nên đường huỷ khi đang chờ duyệt đi qua giá trị resume.
"""

import logging
from collections.abc import Callable, Sequence
from typing import Any

from langgraph.config import get_store
from langgraph.types import interrupt

from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.characters import MAX_REGEN_ROUNDS, slugify
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState

log = logging.getLogger(__name__)

# Cảnh người dùng đã sửa tay: điểm bám nguồn cũ không còn đúng với lời đọc mới.
EDITED_FLAG = "EDITED"


def _wait_for_user(payload: dict[str, Any]) -> tuple[NodeUpdate, dict[str, Any]]:
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        return {}, {}
    if decision.get("cancel"):
        return {"status": "cancelled", "error_code": ErrorCode.CANCELLED.value}, decision
    return {}, decision


def apply_edits(storyboard: dict[str, Any], edits: Any) -> dict[str, Any] | None:
    """Áp các chỉnh sửa lên storyboard. Trả None nếu edits không hợp lệ (cảnh không có, lời đọc
    trống). Cảnh được sửa mất điểm bám nguồn và cờ LOW_FAITHFULNESS, mang cờ EDITED."""
    if not isinstance(edits, list):
        return None
    by_id = {s["id"]: s for s in storyboard.get("scenes", [])}
    updated = dict(by_id)
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("scene_id") not in by_id:
            return None
        narration = edit.get("narration_vi")
        if not isinstance(narration, str) or not narration.strip():
            return None
        on_screen = edit.get("on_screen_text_vi")
        if on_screen is not None and not isinstance(on_screen, str):
            return None
        scene = updated[edit["scene_id"]]
        flags = [f for f in scene.get("flags", []) if f != ErrorCode.LOW_FAITHFULNESS.value]
        updated[edit["scene_id"]] = {
            **scene,
            "narration_vi": narration.strip(),
            "on_screen_text_vi": (on_screen or "").strip() or None,
            "faithfulness": None,
            "unsupported": [],
            "flags": list(dict.fromkeys([*flags, EDITED_FLAG])),
        }
    scenes = [updated[s["id"]] for s in storyboard.get("scenes", [])]
    return {**storyboard, "scenes": scenes}


# Từ id chunk trả `{source_id: {"url", "title"}}` (DB khi chạy thật) để màn duyệt có link nguồn.
SourceLookup = Callable[[Sequence[str]], dict[str, dict[str, Any]]]


def make_review_script(lookup: SourceLookup | None = None) -> NodeFn:
    @node
    def review_script(state: BookReviewState) -> NodeUpdate:
        # Màn duyệt cần đủ storyboard, nguồn trích dẫn (trong từng cảnh), điểm và chi phí.
        storyboard = state.get("storyboard") or {}
        flagged = [
            s["id"]
            for s in storyboard.get("scenes", [])
            if ErrorCode.LOW_FAITHFULNESS in s.get("flags", [])
        ]
        update, decision = _wait_for_user(
            {
                "type": "review_script",
                "message": "Duyệt kịch bản trước khi dựng video.",
                "storyboard": state.get("storyboard"),
                "sources": _sources(storyboard, lookup),
                "eval_scores": state.get("eval_scores") or {},
                "low_faithfulness_scenes": flagged,
                "cost": state.get("cost") or {},
                "cost_estimate": state.get("cost_estimate") or {},
            }
        )
        if update or not decision.get("edits"):
            return update
        feedback = [{"type": "script_edit", "scenes": len(decision["edits"])}]
        edited = apply_edits(storyboard, decision["edits"])
        if edited is None:
            return {"status": "failed", "error_code": ErrorCode.VALIDATION_ERROR.value}
        return {"storyboard": edited, "feedback": feedback}

    return review_script


review_script = make_review_script()


def _sources(storyboard: dict[str, Any], lookup: SourceLookup | None) -> list[dict[str, Any]]:
    """Nguồn được trích, mỗi nguồn kèm id các cảnh dùng nó (và url, tiêu đề nếu tra được)."""
    by_source: dict[str, list[int]] = {}
    chunk_ids: list[str] = []
    for scene in storyboard.get("scenes", []):
        for c in scene.get("citations", []):
            ids = by_source.setdefault(c["source_id"], [])
            if scene["id"] not in ids:
                ids.append(scene["id"])
            chunk_ids.append(c["chunk_id"])
    info = lookup(chunk_ids) if lookup and chunk_ids else {}
    return [{"source_id": k, "scene_ids": v, **info.get(k, {})} for k, v in by_source.items()]


def _valid_picks(picks: Any, candidates: dict[str, Any]) -> dict[str, int]:
    if not isinstance(picks, dict):
        return {}
    out: dict[str, int] = {}
    for slug, idx in picks.items():
        images = (candidates.get(slug) or {}).get("images") or []
        if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(images):
            out[slug] = idx
    return out


def _save_approved(series: str | None, approved: dict[str, dict[str, Any]]) -> None:
    """Ghi nhân vật đã duyệt vào Store để các tập cùng series dùng lại (xem `character_sheets`)."""
    if not series:
        return
    try:
        store = get_store()
    except RuntimeError:  # chạy không có Store (test khung, script)
        return
    for slug, value in approved.items():
        try:
            store.put(("characters", slugify(series)), slug, value)
        except Exception:  # noqa: BLE001
            log.warning("không ghi được nhân vật %s vào Store", slug, exc_info=True)


@node
def review_characters(state: BookReviewState) -> NodeUpdate:
    """Mỗi nhân vật có lưới ứng viên: chọn 1 ảnh hoặc yêu cầu tạo lại (kèm ghi chú). Resume:
    `{"selections": {slug: chỉ số ảnh}, "regenerate": {slug: ghi chú}}`. Có `regenerate` thì
    graph quay về `regen_characters` rồi hỏi lại; không thì mọi nhân vật phải có lựa chọn
    (nhân vật tái dùng từ series đã duyệt thì tự chọn)."""
    candidates = state.get("character_candidates") or {}
    update, decision = _wait_for_user(
        {
            "type": "review_characters",
            "message": "Chọn ảnh cho từng nhân vật.",
            "characters": {
                slug: {**c, "regen_left": max(MAX_REGEN_ROUNDS - int(c.get("round", 0)), 0)}
                for slug, c in candidates.items()
            },
            "picks": state.get("character_picks") or {},
            "cost": state.get("cost") or {},
        }
    )
    if update:
        return update
    picks = _valid_picks(decision.get("selections"), candidates)
    regen = decision.get("regenerate")
    if isinstance(regen, dict) and regen:
        notes = {
            slug: note if isinstance(note, str) else ""
            for slug, note in regen.items()
            if slug in candidates and not candidates[slug].get("reused")
        }
        if notes:
            return {
                "character_regen": notes,
                "character_picks": picks,
                "feedback": [
                    {"type": "character_regen", "slug": slug, "note": note}
                    for slug, note in notes.items()
                    if note
                ],
            }
    approved: dict[str, dict[str, Any]] = {}
    for slug, c in candidates.items():
        idx = 0 if c.get("reused") else picks.get(slug)
        if idx is None or idx >= len(c.get("images") or []):
            return {"status": "failed", "error_code": ErrorCode.VALIDATION_ERROR.value}
        approved[slug] = {"name": c.get("name", slug), "sheet_path": c["images"][idx]}
    series = state["book"].get("series") if "book" in state else None
    _save_approved(series, {k: v for k, v in approved.items() if not candidates[k].get("reused")})
    return {
        "characters_approved": approved,
        "character_regen": None,
        "asset_refs": {
            f"character:{slug}:approved": v["sheet_path"] for slug, v in approved.items()
        },
    }
