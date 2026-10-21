"""Job worker với TTS giả, aligner dự phòng, và hai node tts_align/build_timeline trong graph."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from book_review_api.config import Settings
from book_review_api.graph.nodes.media import (
    make_build_timeline_node,
    make_tts_align_node,
    tts_job_key,
)
from book_review_api.queue import JobFailed
from book_review_worker import jobs
from book_review_worker.providers.aligner import ProportionalAligner
from book_review_worker.providers.base import TTSResult, Word

STORYBOARD = {
    "book": {"title": "Sách thử"},
    "book_category": "non_fiction",
    "spoiler_free": True,
    "hook_vi": "x",
    "style_prompt_en": "flat",
    "caption_vi": "x",
    "scenes": [
        {
            "id": 1,
            "section": "hook",
            "narration_vi": "Một hai ba bốn năm sáu bảy tám chín mười",
            "scene_type": "title",
            "mood": "warm",
            "images": [{"prompt_en": "a"}, {"prompt_en": "b"}],
        },
        {
            "id": 2,
            "section": "body",
            "narration_vi": "Câu thứ hai ngắn hơn",
            "scene_type": "action",
            "mood": "warm",
        },
    ],
}


class FakeTTS:
    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, text: str, out_path: Path) -> TTSResult:
        self.calls += 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"mp3")
        n = len(text.split())
        words = [
            Word(text=t, start_s=0.1 + i * 0.4, end_s=0.1 + (i + 1) * 0.4)
            for i, t in enumerate(text.split())
        ]
        return TTSResult(audio_path=str(out_path), duration_s=0.1 + n * 0.4 + 0.8, words=words)


class WorkerRunner:
    """Gọi thẳng hàm job như arq làm, không cần Redis."""

    def __init__(self, tmp: Path) -> None:
        self.ctx: dict[str, Any] = {"tts": FakeTTS(), "media_dir": str(tmp)}

    def run(self, function: str, payload: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = asyncio.run(getattr(jobs, function)(self.ctx, payload))
        return result


def test_tts_job_writes_files_and_reuses_cache(tmp_path: Path) -> None:
    runner = WorkerRunner(tmp_path)
    payload = {"job_key": "k", "scenes": [{"id": 1, "text": "xin chào các bạn"}]}
    first = runner.run("tts", payload)
    assert (tmp_path / "tts" / "k" / "scene_1.mp3").exists()
    assert first["audio"][0]["words"][0]["text"] == "xin"
    assert first["audio"][0]["audio_path"] == "tts/k/scene_1.mp3"
    second = runner.run("tts", payload)
    assert runner.ctx["tts"].calls == 1
    assert second == first


def test_nodes_produce_timeline_from_storyboard(tmp_path: Path) -> None:
    runner = WorkerRunner(tmp_path)
    settings = Settings(scene_gap_s=0.2)
    out = make_tts_align_node(runner, settings)({"storyboard": STORYBOARD})
    assert set(out["asset_refs"]) == {"tts:1", "tts:2"}
    assert out["cost"]["tts_chars"] > 0
    assert [a["image_count"] for a in out["timeline"]["audio"]] == [2, 1]

    out2 = make_build_timeline_node(runner, settings)({"timeline": out["timeline"]})
    tl = out2["timeline"]
    first, second = tl["scenes"][0], tl["scenes"][1]
    assert first["start_s"] == 0
    assert second["start_s"] == pytest.approx(first["end_s"] + 0.2)
    assert tl["total_duration_s"] == pytest.approx(second["end_s"])


def test_tts_node_fails_cleanly_when_worker_fails() -> None:
    class Broken:
        def run(self, function: str, payload: dict[str, Any]) -> dict[str, Any]:
            raise JobFailed("x")

    out = make_tts_align_node(Broken(), Settings())({"storyboard": STORYBOARD})
    assert out == {"status": "failed", "error_code": "PROVIDER_UNAVAILABLE"}
    assert make_tts_align_node(Broken(), Settings())({})["status"] == "failed"


def test_job_key_depends_on_text_and_voice() -> None:
    assert tts_job_key(["a"], "v1") == tts_job_key(["a"], "v1")
    assert tts_job_key(["a"], "v1") != tts_job_key(["b"], "v1")
    assert tts_job_key(["a"], "v1") != tts_job_key(["a"], "v2")


def test_proportional_aligner_covers_speech_span() -> None:
    words = ProportionalAligner().align(Path("x.mp3"), "một hai ba bốn", 5.0)
    assert [w.text for w in words] == ["một", "hai", "ba", "bốn"]
    assert words[0].start_s == pytest.approx(0.1)
    assert words[-1].end_s == pytest.approx(4.2)
    assert all(a.end_s == pytest.approx(b.start_s) for a, b in zip(words, words[1:], strict=False))
    assert ProportionalAligner().align(Path("x.mp3"), "", 5.0) == []
