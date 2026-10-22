"""Node media: tts_align, build_timeline (ngày 12), subtitles, scene_images, motion,
compose_render (ngày 13). Mỗi node gửi job sang worker và chờ kết quả."""

import hashlib
import json
from typing import Any

from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.state import BookReviewState
from book_review_api.queue import JobFailed, JobRunner
from book_review_api.storyboard.images import image_plan
from book_review_api.storyboard.schema import SceneImage, Storyboard


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
        # Cùng kế hoạch với node `scene_images` để `Shot.image_ref` luôn trỏ tới ảnh có thật.
        image_counts = image_plan(sb, cfg)
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


def timeline_key(timeline: dict[str, Any]) -> str:
    """Khoá thư mục render theo nội dung timeline."""
    digest = hashlib.sha1(json.dumps(timeline, sort_keys=True).encode()).hexdigest()
    return digest[:16]


def _timeline_of(state: BookReviewState) -> dict[str, Any] | None:
    tl = state.get("timeline") or {}
    return tl if tl.get("scenes") else None


def make_subtitles_node(runner: JobRunner) -> NodeFn:
    @node
    def subtitles(state: BookReviewState) -> NodeUpdate:
        tl = _timeline_of(state)
        if tl is None:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        try:
            result = runner.run("subtitles", {"job_key": timeline_key(tl), "timeline": tl})
        except JobFailed:
            return {"status": "failed", "error_code": ErrorCode.RENDER_FAILED.value}
        return {"asset_refs": {"subtitles:ass": result["ass"], "subtitles:srt": result["srt"]}}

    return subtitles


def make_scene_images_node(runner: JobRunner) -> NodeFn:
    @node
    def scene_images(state: BookReviewState) -> NodeUpdate:
        storyboard = state.get("storyboard")
        if not storyboard:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        sb = Storyboard.model_validate(storyboard)
        items = [
            {
                "scene_id": s.id,
                "image_ref": ref,
                "label": s.on_screen_text_vi or (img.prompt_en if s.images else s.narration_vi),
                "mood": s.mood,
            }
            for s in sb.scenes
            for ref, img in enumerate(s.images or [SceneImage(prompt_en="")])
        ]
        key = hashlib.sha1(json.dumps(items, sort_keys=True).encode()).hexdigest()[:16]
        try:
            result = runner.run("images", {"job_key": key, "images": items})
        except JobFailed:
            return {"status": "failed", "error_code": ErrorCode.RENDER_FAILED.value}
        return {"asset_refs": {f"image:{k}": v for k, v in result["images"].items()}}

    return scene_images


def make_motion_node(runner: JobRunner) -> NodeFn:
    @node
    def motion(state: BookReviewState) -> NodeUpdate:
        tl = _timeline_of(state)
        refs = state.get("asset_refs") or {}
        images = {k.removeprefix("image:"): v for k, v in refs.items() if k.startswith("image:")}
        if tl is None or not images:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        try:
            result = runner.run(
                "motion", {"job_key": timeline_key(tl), "timeline": tl, "images": images}
            )
        except JobFailed:
            return {"status": "failed", "error_code": ErrorCode.RENDER_FAILED.value}
        return {"timeline": {**tl, "clips": result["clips"]}}

    return motion


def make_compose_render_node(runner: JobRunner) -> NodeFn:
    @node
    def compose_render(state: BookReviewState) -> NodeUpdate:
        tl = _timeline_of(state)
        clips = (tl or {}).get("clips")
        if tl is None or not clips:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        try:
            result = runner.run(
                "compose", {"job_key": timeline_key(tl), "timeline": tl, "clips": clips}
            )
        except JobFailed:
            return {"status": "failed", "error_code": ErrorCode.RENDER_FAILED.value}
        return {"asset_refs": {"video:raw": result["video"]}}

    return compose_render
