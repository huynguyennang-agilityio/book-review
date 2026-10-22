"""Các job arq: tts, timeline, subtitles, images (placeholder), motion (Ken Burns), compose."""

import json
from pathlib import Path
from typing import Any

from book_review_worker.media.cover import make_cover
from book_review_worker.media.ffmpeg import (
    XFADE_S,
    burn_overlay,
    concat_xfade,
    make_music,
    mux_audio,
    probe_duration,
    render_clip,
)
from book_review_worker.media.kenburns import DIRECTIONS
from book_review_worker.media.overlay import Highlight, render_overlay_track
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
    """payload: {"job_key", "timeline", "karaoke"?}. Ghi `subtitles.ass` và `subtitles.srt`."""
    media_dir = Path(ctx["media_dir"])
    tl = Timeline.model_validate(payload["timeline"])
    ass, srt, cues = write_subtitles(
        tl, _render_dir(ctx, payload), karaoke=bool(payload.get("karaoke"))
    )
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


FINAL_NAME = "final_review.mp4"
VOICE_ONLY_NAME = "final_review_voice_only.mp4"
COVER_NAME = "cover.jpg"


async def compose(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Ghép clip (xfade), burn phụ đề + chữ nổi bật trong safe zone, đặt audio theo offset.

    payload: {"job_key", "timeline", "clips", "title"?, "hook"?, "highlights"?: [{text, start_s,
    end_s}], "karaoke"?: bool, "music"?: bool}. Xuất bản có nhạc nền (ducking), bản voice-only
    (không nhạc, để gắn nhạc trong app TikTok) và `cover.jpg`. Đường dẫn trả về tương đối."""
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
    await report_progress(ctx, 1, 4, "ghép shot")
    cues = build_cues(tl)
    highlights = [Highlight.model_validate(h) for h in payload.get("highlights", [])]
    listing = render_overlay_track(
        cues,
        highlights,
        work / "overlay",
        tl.total_duration_s,
        karaoke=bool(payload.get("karaoke")),
    )
    burned = work / "burned.mp4"
    burn_overlay(raw, listing, tl.total_duration_s, burned)
    await report_progress(ctx, 2, 4, "phụ đề và chữ nổi bật")
    voice_only = work / VOICE_ONLY_NAME
    mux_audio(burned, tl, media_dir, voice_only)
    final = work / FINAL_NAME
    if payload.get("music", True):
        music = make_music(
            media_dir / "music" / f"ambient_{int(tl.total_duration_s) + 2}s.m4a",
            tl.total_duration_s + 2,
        )
        mux_audio(burned, tl, media_dir, final, music)
    else:
        final.write_bytes(voice_only.read_bytes())
    await report_progress(ctx, 3, 4, "âm thanh")
    cover = work / COVER_NAME
    make_cover(raw, payload.get("title", ""), payload.get("hook", ""), cover)
    await report_progress(ctx, 4, 4, "xong")
    return {
        "video": _rel(media_dir, final),
        "voice_only": _rel(media_dir, voice_only),
        "cover": _rel(media_dir, cover),
        "duration_s": probe_duration(final),
    }


async def package(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Ghi các file văn bản đầu ra. payload: {"job_key", "caption_vi", "hashtags", "sources_md",
    "project": {...}}. Trả đường dẫn tương đối của `caption.txt`, `sources.md`, `project.json`."""
    media_dir = Path(ctx["media_dir"])
    work = _render_dir(ctx, payload)
    work.mkdir(parents=True, exist_ok=True)
    tags = " ".join(h if h.startswith("#") else f"#{h}" for h in payload.get("hashtags", []))
    caption = work / "caption.txt"
    caption.write_text(
        f"{payload.get('caption_vi', '').strip()}\n\n{tags}\n".rstrip() + "\n", encoding="utf-8"
    )
    sources = work / "sources.md"
    sources.write_text(payload.get("sources_md", ""), encoding="utf-8")
    project = work / "project.json"
    project.write_text(
        json.dumps(payload.get("project", {}), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "caption": _rel(media_dir, caption),
        "sources": _rel(media_dir, sources),
        "project": _rel(media_dir, project),
    }


__all__ = ["compose", "images", "motion", "package", "subtitles", "timeline", "tts"]
