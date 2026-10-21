"""Node `tts_align` và `build_timeline` (ngày 12): gửi job sang worker, chờ kết quả."""

import hashlib
from typing import Any

from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.queue import JobFailed, JobRunner
from book_review_api.storyboard.schema import Storyboard


def tts_job_key(texts: list[str], voice: str) -> str:
    """Khoá theo nội dung: cùng kịch bản và giọng thì worker dùng lại audio đã có."""
    digest = hashlib.sha1("\x1f".join([voice, *texts]).encode()).hexdigest()
    return digest[:16]


def make_tts_align_node(runner: JobRunner, settings: Settings | None = None) -> NodeFn:
    @node
    def tts_align(state: BookReviewState) -> NodeUpdate:
        cfg = settings or get_settings()
        storyboard = state.get("storyboard")
        if not storyboard:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        sb = Storyboard.model_validate(storyboard)
        texts = [s.narration_vi for s in sb.scenes]
        payload: dict[str, Any] = {
            "job_key": tts_job_key(texts, cfg.tts_voice),
            "scenes": [{"id": s.id, "text": s.narration_vi} for s in sb.scenes],
        }
        try:
            result = runner.run("tts", payload)
        except JobFailed:
            return {"status": "failed", "error_code": ErrorCode.PROVIDER_UNAVAILABLE.value}
        audio: list[dict[str, Any]] = result["audio"]
        image_counts = {s.id: max(len(s.images), 1) for s in sb.scenes}
        for item in audio:
            item["image_count"] = image_counts[item["scene_id"]]
        return {
            "timeline": {"audio": audio},
            "asset_refs": {f"tts:{a['scene_id']}": a["audio_path"] for a in audio},
            "cost": {"tts_chars": float(sum(len(t) for t in texts))},
        }

    return tts_align


def make_build_timeline_node(runner: JobRunner, settings: Settings | None = None) -> NodeFn:
    @node
    def build_timeline(state: BookReviewState) -> NodeUpdate:
        cfg = settings or get_settings()
        audio = (state.get("timeline") or {}).get("audio")
        if not audio:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        try:
            result = runner.run("timeline", {"audio": audio, "gap_s": cfg.scene_gap_s})
        except JobFailed:
            return {"status": "failed", "error_code": ErrorCode.RENDER_FAILED.value}
        return {"timeline": {"audio": audio, **result}}

    return build_timeline
