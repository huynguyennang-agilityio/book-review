"""edge-tts: câu bị từ chối thì thử các biến thể trước khi báo lỗi."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from book_review_worker.providers.base import Word
from book_review_worker.providers.tts_edge import EdgeTTS, EdgeTTSError, text_variants


class Scripted(EdgeTTS):
    def __init__(self, accept: Any) -> None:
        self.waits: list[float] = []

        async def sleep(s: float) -> None:
            self.waits.append(s)

        super().__init__(sleep=sleep)
        self.accept = accept
        self.sent: list[tuple[str, bool]] = []

    async def _stream(self, text: str, out_path: Path, word_boundary: bool = True) -> list[Word]:
        self.sent.append((text, word_boundary))
        if not self.accept(text):
            raise EdgeTTSError("No audio was received")
        return [Word(text="x", start_s=0, end_s=1)] if word_boundary else []


def run(tts: EdgeTTS, text: str) -> list[Word]:
    return asyncio.run(tts._stream_with_retry(text, Path("/tmp/x.mp3")))


def test_rejected_sentence_falls_back_to_prefixed_variant_without_word_boundary() -> None:
    tts = Scripted(lambda t: t.startswith("…"))
    words = run(tts, "Trung tâm truyện là cô ấy.")
    assert tts.sent == [
        ("Trung tâm truyện là cô ấy.", True),
        ("Trung tâm truyện là cô ấy.", True),
        ("… Trung tâm truyện là cô ấy.", False),
    ]
    assert words == []  # aligner dự phòng chia theo câu gốc
    assert tts.waits == [2, 4]


def test_first_try_ok_keeps_word_boundary() -> None:
    tts = Scripted(lambda t: True)
    assert len(run(tts, "Xin chào.")) == 1
    assert tts.waits == []


def test_all_variants_rejected_raises() -> None:
    tts = Scripted(lambda t: False)
    with pytest.raises(EdgeTTSError):
        run(tts, "Câu lỗi.")
    assert len(tts.sent) == len(text_variants("Câu lỗi.")) == 6
    assert tts.waits == [2, 4, 8, 8, 8]
