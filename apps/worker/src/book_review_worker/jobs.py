"""Các job arq. `tts` và `timeline` làm thật; `images`, `motion`, `compose` còn là stub."""

import json
from pathlib import Path
from typing import Any

from book_review_worker.media.timeline import SceneAudio, build_timeline
from book_review_worker.progress import report_progress
from book_review_worker.providers.base import TTSProvider, TTSResult

STUB = {"status": "stub"}


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


async def images(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return STUB


async def motion(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return STUB


async def compose(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return STUB


__all__ = ["compose", "images", "motion", "timeline", "tts"]
