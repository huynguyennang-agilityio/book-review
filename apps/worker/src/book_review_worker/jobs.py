"""Các job arq: tts, timeline, subtitles, images (placeholder), motion (Ken Burns), compose."""

import json
from pathlib import Path
from typing import Any

from book_review_worker.media.ffmpeg import (
    XFADE_S,
    compose_final,
    concat_xfade,
    probe_duration,
    render_clip,
    render_subtitle_pngs,
)
from book_review_worker.media.kenburns import DIRECTIONS
from book_review_worker.media.placeholder import make_placeholder
from book_review_worker.media.subtitles import build_cues, write_subtitles
from book_review_worker.media.timeline import SceneAudio, Timeline, build_timeline
from book_review_worker.progress import report_progress
from book_review_worker.providers.base import TTSProvider, TTSResult


async def tts(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Đọc từng cảnh thành mp3 + words.json.

    payload: {"job_key": str, "scenes": [{"id": int, "text": str}]}.
    Kết quả nằm trong `<media_dir>/tts/<job_key>/`; file đã có thì dùng lại, nên chạy lại
    cùng kịch bản không tốn thêm lượt gọi edge-tts. `audio_path` trả về là đường dẫn tương
    đối so với `media_dir`, vì API và worker (container) gắn thư mục này ở chỗ khác nhau.
    """
    provider: TTSProvider = ctx["tts"]
    media_dir = Path(ctx["media_dir"])
    out_dir = media_dir / "tts" / payload["job_key"]
    scenes: list[dict[str, Any]] = payload["scenes"]
    results: list[dict[str, Any]] = []
    for i, scene in enumerate(scenes):
        mp3 = out_dir / f"scene_{scene['id']}.mp3"
        meta = mp3.with_suffix(".json")
        if mp3.exists() and meta.exists():
            result = TTSResult.model_validate_json(meta.read_text(encoding="utf-8"))
        else:
            result = await provider.synthesize(scene["text"], mp3)
            meta.write_text(result.model_dump_json(), encoding="utf-8")
        rel = mp3.relative_to(media_dir).as_posix()
        results.append({"scene_id": scene["id"], **result.model_dump(), "audio_path": rel})
        await report_progress(ctx, i + 1, len(scenes), f"tts cảnh {scene['id']}")
    return {"audio": results}


async def timeline(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"audio": [SceneAudio...], "gap_s": float}. Trả Timeline dạng dict."""
    audios = [SceneAudio.model_validate(a) for a in payload["audio"]]
    result = build_timeline(audios, gap_s=payload.get("gap_s", 0.2))
    dumped: dict[str, Any] = json.loads(result.model_dump_json())
    return dumped


def _rel(media_dir: Path, path: Path) -> str:
    return path.relative_to(media_dir).as_posix()


def _render_dir(ctx: dict[str, Any], payload: dict[str, Any]) -> Path:
    return Path(ctx["media_dir"]) / "render" / str(payload["job_key"])


async def subtitles(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"job_key", "timeline"}. Ghi `subtitles.ass` và `subtitles.srt`."""
    media_dir = Path(ctx["media_dir"])
    tl = Timeline.model_validate(payload["timeline"])
    ass, srt, cues = write_subtitles(tl, _render_dir(ctx, payload))
    return {"ass": _rel(media_dir, ass), "srt": _rel(media_dir, srt), "cues": len(cues)}


async def images(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Ảnh placeholder cho mỗi ảnh của cảnh. payload: {"job_key", "images": [{"scene_id",
    "image_ref", "label", "mood"}]}. Ảnh thật (Fal) thay vào đây ở các ngày sau."""
    media_dir = Path(ctx["media_dir"])
    out_dir = media_dir / "images" / payload["job_key"]
    result: dict[str, str] = {}
    items: list[dict[str, Any]] = payload["images"]
    for i, item in enumerate(items):
        path = out_dir / f"scene_{item['scene_id']}_{item['image_ref']}.png"
        if not path.exists():
            make_placeholder(path, item["label"], item["mood"])
        result[f"{item['scene_id']}:{item['image_ref']}"] = _rel(media_dir, path)
        await report_progress(ctx, i + 1, len(items), f"ảnh cảnh {item['scene_id']}")
    return {"images": result}


async def motion(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Ken Burns cho từng shot. payload: {"job_key", "timeline", "images": {"scene:ref": path}}.

    Clip của mọi shot trừ shot cuối dài thêm `XFADE_S` để bù phần chồng khi ghép."""
    media_dir = Path(ctx["media_dir"])
    tl = Timeline.model_validate(payload["timeline"])
    out_dir = _render_dir(ctx, payload) / "clips"
    shots = [(s.scene_id, sh) for s in tl.scenes for sh in s.shots]
    clips: list[dict[str, Any]] = []
    for i, (scene_id, shot) in enumerate(shots):
        last = i == len(shots) - 1
        duration = shot.end_s - shot.start_s + (0.0 if last else XFADE_S)
        image = media_dir / payload["images"][f"{scene_id}:{shot.image_ref}"]
        clip = out_dir / f"clip_{i:03d}.mp4"
        if not clip.exists():
            render_clip(image, duration, DIRECTIONS[i % len(DIRECTIONS)], clip)
        clips.append({"path": _rel(media_dir, clip), "start_s": shot.start_s, "end_s": shot.end_s})
        await report_progress(ctx, i + 1, len(shots), f"motion shot {i + 1}")
    return {"clips": clips}


async def compose(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Ghép clip (xfade), đặt audio theo offset, burn phụ đề. payload: {"job_key", "timeline",
    "clips": [...]}. Trả `video` (đường dẫn tương đối) và độ dài đo bằng ffprobe."""
    media_dir = Path(ctx["media_dir"])
    tl = Timeline.model_validate(payload["timeline"])
    work = _render_dir(ctx, payload)
    clips = payload["clips"]
    raw = work / "raw_video.mp4"
    concat_xfade(
        [media_dir / c["path"] for c in clips],
        [c["start_s"] for c in clips],
        [c["end_s"] for c in clips],
        raw,
    )
    await report_progress(ctx, 1, 3, "ghép shot")
    cues = build_cues(tl)
    listing = render_subtitle_pngs(cues, work / "subs", tl.total_duration_s)
    await report_progress(ctx, 2, 3, "phụ đề")
    final = work / "video.mp4"
    compose_final(raw, tl, media_dir, listing, final)
    await report_progress(ctx, 3, 3, "xong")
    return {"video": _rel(media_dir, final), "duration_s": probe_duration(final)}


__all__ = ["compose", "images", "motion", "subtitles", "timeline", "tts"]
