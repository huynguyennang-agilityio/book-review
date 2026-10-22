"""Node media: tts_align, build_timeline (ngày 12), subtitles, scene_images, motion,
compose_render (ngày 13). Mỗi node gửi job sang worker và chờ kết quả."""

import hashlib
import json
from collections.abc import Callable, Sequence
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
            result = runner.run(
                "subtitles",
                {
                    "job_key": timeline_key(tl),
                    "timeline": tl,
                    "karaoke": bool((state.get("options") or {}).get("karaoke", False)),
                },
            )
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


HOOK_SHOW_S = 5.0
ONSCREEN_SHOW_S = 3.0


def highlights_for(storyboard: dict[str, Any], tl: dict[str, Any]) -> list[dict[str, Any]]:
    """Chữ nổi bật theo timeline tuyệt đối: hook 5 giây đầu, chữ trên màn hình của các cảnh khác
    3 giây đầu cảnh (không vượt hết cảnh)."""
    by_id = {s["id"]: s for s in storyboard.get("scenes", [])}
    out: list[dict[str, Any]] = []
    for ts in tl.get("scenes", []):
        scene = by_id.get(ts["scene_id"]) or {}
        is_hook = scene.get("section") == "hook"
        text = (scene.get("on_screen_text_vi") or "").strip()
        if is_hook:
            text = (storyboard.get("hook_vi") or "").strip() or text
        if not text:
            continue
        show = HOOK_SHOW_S if is_hook else ONSCREEN_SHOW_S
        out.append(
            {
                "text": text,
                "start_s": ts["start_s"],
                "end_s": min(ts["start_s"] + show, ts["end_s"]),
            }
        )
    return out


def sources_markdown(storyboard: dict[str, Any], info: dict[str, dict[str, Any]]) -> str:
    """`sources.md`: nguồn và trích dẫn theo cảnh."""
    title = storyboard.get("book", {}).get("title", "")
    lines = [f"# Nguồn: {title}", ""]
    seen: dict[str, dict[str, Any]] = {}
    for scene in storyboard.get("scenes", []):
        for c in scene.get("citations", []):
            seen.setdefault(c["source_id"], info.get(c["source_id"], {}))
    if not seen:
        return "\n".join([*lines, "Kịch bản không có trích dẫn.", ""])
    lines += ["## Danh sách nguồn", ""]
    for sid, meta in seen.items():
        label = meta.get("title") or sid
        url = meta.get("url")
        lines.append(f"- [{label}]({url})" if url else f"- {label}")
    lines += ["", "## Trích dẫn theo cảnh", ""]
    for scene in storyboard.get("scenes", []):
        cites = scene.get("citations", [])
        if not cites:
            continue
        lines.append(f"### Cảnh {scene['id']} ({scene.get('section', '')})")
        for c in cites:
            label = seen.get(c["source_id"], {}).get("title") or c["source_id"]
            lines.append(f'- {label}: "{c["quote"]}"')
        lines.append("")
    return "\n".join(lines)


def make_compose_render_node(
    runner: JobRunner,
    source_lookup: Callable[[Sequence[str]], dict[str, dict[str, Any]]] | None = None,
) -> NodeFn:
    @node
    def compose_render(state: BookReviewState) -> NodeUpdate:
        tl = _timeline_of(state)
        clips = (tl or {}).get("clips")
        storyboard = state.get("storyboard") or {}
        if tl is None or not clips:
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        options = state.get("options") or {}
        key = timeline_key(tl)
        hook = (storyboard.get("hook_vi") or "").strip()
        try:
            result = runner.run(
                "compose",
                {
                    "job_key": key,
                    "timeline": tl,
                    "clips": clips,
                    "title": storyboard.get("book", {}).get("title", ""),
                    "hook": hook,
                    "highlights": highlights_for(storyboard, tl),
                    "karaoke": bool(options.get("karaoke", False)),
                },
            )
            chunk_ids = [
                c["chunk_id"] for s in storyboard.get("scenes", []) for c in s.get("citations", [])
            ]
            info = source_lookup(chunk_ids) if source_lookup and chunk_ids else {}
            refs = state.get("asset_refs") or {}
            assets = {
                **refs,
                "video:final": result["video"],
                "video:voice_only": result["voice_only"],
                "cover": result["cover"],
            }
            pkg = runner.run(
                "package",
                {
                    "job_key": key,
                    "caption_vi": storyboard.get("caption_vi", ""),
                    "hashtags": storyboard.get("hashtags", []),
                    "sources_md": sources_markdown(storyboard, info),
                    "project": {
                        "storyboard": storyboard,
                        "timeline": {k: v for k, v in tl.items() if k != "audio"},
                        "asset_refs": assets,
                        "cost": state.get("cost") or {},
                        "duration_s": result["duration_s"],
                    },
                },
            )
        except JobFailed:
            return {"status": "failed", "error_code": ErrorCode.RENDER_FAILED.value}
        return {
            "asset_refs": {
                "video:raw": result["video"],
                "video:final": result["video"],
                "video:voice_only": result["voice_only"],
                "cover": result["cover"],
                "caption": pkg["caption"],
                "sources": pkg["sources"],
                "project": pkg["project"],
            }
        }

    return compose_render
