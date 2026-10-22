"""Ngày 19: safe zone, karaoke, nhạc + ducking, bản voice-only, cover và file văn bản."""

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from test_render import make_audio, words

from book_review_worker import jobs
from book_review_worker.media.ffmpeg import probe_duration
from book_review_worker.media.kenburns import H, W
from book_review_worker.media.overlay import (
    RIGHT_PX,
    SAFE_Y0,
    SAFE_Y1,
    render_frame,
)
from book_review_worker.media.subtitles import SubtitleCue, build_cues, render_ass
from book_review_worker.media.timeline import SceneAudio, build_timeline

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="cần ffmpeg")

LONG = "Một câu rất dài để thử việc xuống dòng trong vùng an toàn của khung hình dọc"


def mean_volume(path: Path) -> float:
    err = subprocess.run(
        ["ffmpeg", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr  # fmt: skip
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", err).group(1))  # type: ignore[union-attr]


def test_text_stays_inside_safe_zone() -> None:
    cue = SubtitleCue(text=LONG, start_s=0, end_s=3, words=[(w, 0, 1) for w in LONG.split()])
    img = render_frame(cue, active=3, highlight=LONG, karaoke=True)
    left, top, right, bottom = img.getchannel("A").getbbox()  # type: ignore[misc]
    assert right <= W - RIGHT_PX + 1
    assert top >= SAFE_Y0
    assert bottom <= SAFE_Y1


def test_karaoke_marks_words_in_ass() -> None:
    tl = build_timeline([SceneAudio(scene_id=1, audio_path="a", duration_s=4.0, words=words(8))])
    cues = build_cues(tl)
    assert all(len(c.words) == len(c.text.split()) for c in cues)
    plain, karaoke = render_ass(cues), render_ass(cues, karaoke=True)
    assert "\\k" not in plain
    assert karaoke.count("\\k") == sum(len(c.words) for c in cues)


def test_karaoke_highlights_only_spoken_words() -> None:
    cue = SubtitleCue(text="aaa bbb ccc", start_s=0, end_s=3, words=[("aaa", 0, 1), ("bbb", 1, 2)])
    none = render_frame(cue, active=None, highlight=None, karaoke=True)
    one = render_frame(cue, active=0, highlight=None, karaoke=True)
    assert none.tobytes() != one.tobytes()


def test_compose_writes_music_voice_only_and_cover(tmp_path: Path) -> None:
    media = tmp_path / "media"
    (media / "tts").mkdir(parents=True)
    audios = []
    for sid, secs in ((1, 6.0), (2, 4.0)):
        make_audio(media / "tts" / f"s{sid}.mp3", secs)
        audios.append(
            SceneAudio(
                scene_id=sid,
                audio_path=f"tts/s{sid}.mp3",
                duration_s=secs,
                words=words(int((secs - 0.5) / 0.45)),
            )
        )
    tl = build_timeline(audios)
    timeline: dict[str, Any] = tl.model_dump()
    ctx: dict[str, Any] = {"media_dir": str(media)}

    async def run() -> tuple[dict[str, Any], dict[str, Any]]:
        imgs = await jobs.images(
            ctx,
            {
                "job_key": "k",
                "images": [
                    {"scene_id": 1, "image_ref": 0, "label": "Một", "mood": "warm"},
                    {"scene_id": 2, "image_ref": 0, "label": "Hai", "mood": "calm"},
                ],
            },
        )
        mot = await jobs.motion(
            ctx, {"job_key": "k", "timeline": timeline, "images": imgs["images"]}
        )
        out = await jobs.compose(
            ctx,
            {
                "job_key": "k",
                "timeline": timeline,
                "clips": mot["clips"],
                "title": "Nhà giả kim",
                "hook": "Một cuốn sách đổi đời",
                "highlights": [{"text": "Hook lớn", "start_s": 0.0, "end_s": 3.0}],
                "karaoke": True,
            },
        )
        pkg = await jobs.package(
            ctx,
            {
                "job_key": "k",
                "caption_vi": "Review sách hay.",
                "hashtags": ["review", "#sach"],
                "sources_md": "# Nguồn\n",
                "project": {"a": 1},
            },
        )
        return out, pkg

    result, pkg = asyncio.run(run())
    final, voice = media / result["video"], media / result["voice_only"]
    assert final.name == "final_review.mp4" and voice.name == "final_review_voice_only.mp4"
    for video in (final, voice):
        assert abs(probe_duration(video) - tl.total_duration_s) <= 0.1
    # Bản có nhạc khác bản voice-only (có thêm nhạc nền).
    assert abs(mean_volume(final) - mean_volume(voice)) > 0.1
    cover = Image.open(media / result["cover"])
    assert cover.size == (W, H) and cover.format == "JPEG"
    assert (media / pkg["caption"]).read_text(encoding="utf-8") == (
        "Review sách hay.\n\n#review #sach\n"
    )
    assert (media / pkg["sources"]).read_text(encoding="utf-8").startswith("# Nguồn")
    assert json.loads((media / pkg["project"]).read_text(encoding="utf-8")) == {"a": 1}
