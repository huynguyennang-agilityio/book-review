"""TTS bằng edge-tts: giọng vi-VN, WordBoundary làm nguồn word timing (ADR 0002)."""

import asyncio
import logging
from pathlib import Path

import edge_tts

from book_review_worker.media.ffmpeg import probe_duration
from book_review_worker.providers.aligner import ProportionalAligner
from book_review_worker.providers.base import Aligner, TTSResult, Word

log = logging.getLogger(__name__)

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
# edge-tts trả offset/duration theo đơn vị 100 ns.
_TICKS_PER_SECOND = 10_000_000


class EdgeTTSError(Exception):
    """edge-tts lỗi mạng hoặc không trả audio sau khi thử lại."""


class EdgeTTS:
    """Giới hạn 2 request song song tới edge-tts (plan v5, mục Rate limit)."""

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        concurrency: int = 2,
        attempts: int = 3,
        fallback_aligner: Aligner | None = None,
    ) -> None:
        self.voice = voice
        self._sem = asyncio.Semaphore(concurrency)
        self._attempts = attempts
        self._fallback = fallback_aligner or ProportionalAligner()

    async def synthesize(self, text: str, out_path: Path) -> TTSResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._sem:
            words = await self._stream_with_retry(text, out_path)
        duration = probe_duration(out_path)
        if not words:
            log.warning("edge-tts không trả WordBoundary, dùng aligner dự phòng")
            words = self._fallback.align(out_path, text, duration)
        return TTSResult(audio_path=str(out_path), duration_s=duration, words=words)

    async def _stream_with_retry(self, text: str, out_path: Path) -> list[Word]:
        last: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                return await self._stream(text, out_path)
            except Exception as exc:  # edge-tts ném nhiều loại lỗi mạng/websocket
                last = exc
                log.warning("edge-tts lần %d/%d lỗi: %s", attempt, self._attempts, exc)
                await asyncio.sleep(2**attempt)
        raise EdgeTTSError(str(last)) from last

    async def _stream(self, text: str, out_path: Path) -> list[Word]:
        comm = edge_tts.Communicate(text, self.voice, boundary="WordBoundary")
        words: list[Word] = []
        got_audio = False
        with out_path.open("wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    got_audio = True
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / _TICKS_PER_SECOND
                    words.append(
                        Word(
                            text=chunk["text"],
                            start_s=start,
                            end_s=start + chunk["duration"] / _TICKS_PER_SECOND,
                        )
                    )
        if not got_audio:
            raise EdgeTTSError("edge-tts không trả audio")
        return words
