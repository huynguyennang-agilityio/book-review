"""Render thật bằng ffmpeg: phụ đề, ghép shot, độ dài khớp tiếng, không frame đen."""

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from book_review_worker import jobs
from book_review_worker.media.ffmpeg import probe_duration
from book_review_worker.media.subtitles import (
    CHUNK_MAX_CHARS,
    build_cues,
    chunk_words,
    render_ass,
    render_srt,
)
from book_review_worker.media.timeline import SceneAudio, build_timeline
from book_review_worker.providers.base import Word

BLACKDETECT = "blackdetect=d=0.04:pix_th=0.05"
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="cần ffmpeg")


def make_audio(path: Path, seconds: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"sine=frequency=300:duration={seconds}", str(path)],
        check=True,
    )  # fmt: skip


def words(n: int, start: float = 0.1, step: float = 0.45) -> list[Word]:
    return [
        Word(text=f"từ{i}", start_s=start + i * step, end_s=start + (i + 1) * step)
        for i in range(n)
    ]


def test_chunks_are_20_to_25_chars() -> None:
    ws = [(w.text, w.start_s, w.end_s) for w in words(30)]
    chunks = chunk_words(ws)
    assert "".join(c[0] for c in chunks).replace(" ", "") == "".join(w[0] for w in ws)
    for text, _, _ in chunks[:-1]:
        assert 20 <= len(text) <= CHUNK_MAX_CHARS


def test_ass_and_srt_use_absolute_times() -> None:
    tl = build_timeline(
        [
            SceneAudio(scene_id=1, audio_path="a", duration_s=4.0, words=words(8)),
            SceneAudio(scene_id=2, audio_path="b", duration_s=4.0, words=words(8)),
        ]
    )
    cues = build_cues(tl)
    assert cues[-1].start_s > tl.scenes[1].start_s - 1e-6
    assert "Dialogue:" in render_ass(cues)
    assert "-->" in render_srt(cues)


def test_pipeline_video_matches_audio_and_has_no_black_frames(tmp_path: Path) -> None:
    media = tmp_path / "media"
    (media / "tts").mkdir(parents=True)
    audios = []
    for sid, secs in ((1, 7.0), (2, 4.0)):
        make_audio(media / "tts" / f"s{sid}.mp3", secs)
        audios.append(
            SceneAudio(
                scene_id=sid,
                audio_path=f"tts/s{sid}.mp3",
                duration_s=secs,
                words=words(int((secs - 0.5) / 0.45)),
                image_count=2 if sid == 1 else 1,
            )
        )
    tl = build_timeline(audios)
    timeline: dict[str, Any] = tl.model_dump()
    ctx: dict[str, Any] = {"media_dir": str(media)}

    async def run() -> dict[str, Any]:
        imgs = await jobs.images(
            ctx,
            {
                "job_key": "k",
                "images": [
                    {"scene_id": 1, "image_ref": 0, "label": "Cảnh một", "mood": "warm"},
                    {"scene_id": 1, "image_ref": 1, "label": "Cảnh một b", "mood": "warm"},
                    {"scene_id": 2, "image_ref": 0, "label": "Cảnh hai", "mood": "calm"},
                ],
            },
        )
        subs = await jobs.subtitles(ctx, {"job_key": "k", "timeline": timeline})
        assert (media / subs["ass"]).exists() and (media / subs["srt"]).exists()
        mot = await jobs.motion(
            ctx, {"job_key": "k", "timeline": timeline, "images": imgs["images"]}
        )
        return await jobs.compose(
            ctx, {"job_key": "k", "timeline": timeline, "clips": mot["clips"]}
        )

    result = asyncio.run(run())
    video = media / result["video"]
    assert abs(probe_duration(video) - tl.total_duration_s) <= 0.05

    # Không có frame đen: blackdetect không báo đoạn nào.
    out = subprocess.run(
        ["ffmpeg", "-i", str(video), "-vf", BLACKDETECT, "-an", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stderr  # fmt: skip
    assert "black_start" not in out

    # Có tiếng đúng chỗ: stream audio dài bằng video.
    audio_len = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert abs(float(audio_len) - tl.total_duration_s) <= 0.1
