"""TTS bằng edge-tts: giọng vi-VN, WordBoundary làm nguồn word timing (ADR 0002)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
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


def text_variants(text: str) -> list[tuple[str, bool]]:
    """Các cách gửi cùng một câu cho edge-tts, theo thứ tự thử: (câu gửi đi, có WordBoundary).

    edge-tts (giọng HoaiMy) từ chối hẳn một số câu ("No audio was received") dù gửi lại bao
    nhiêu lần, nhưng nhận cùng câu đó khi viết thường hoặc thêm "… " ở đầu (đo trên 15 câu lỗi:
    13/15 qua). Các biến thể không lấy WordBoundary vì chữ đã đổi; aligner dự phòng chia thời
    gian theo câu gốc nên phụ đề vẫn đúng chữ hoa."""
    return [
        (text, True),
        (text, True),
        (f"… {text}", False),
        (text.lower(), False),
        (f"… {text.lower()}", False),
        (text, False),
    ]


class EdgeTTS:
    """Giới hạn 2 request song song tới edge-tts (plan v5, mục Rate limit).

    Mỗi câu thử lần lượt các biến thể của `text_variants`, chờ 2, 4, 8, 8, 8 s giữa các lần.
    """

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        concurrency: int = 2,
        fallback_aligner: Aligner | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.voice = voice
        self._sem = asyncio.Semaphore(concurrency)
        self._fallback = fallback_aligner or ProportionalAligner()
        self._sleep = sleep

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
        variants = text_variants(text)
        for attempt, (sent, word_boundary) in enumerate(variants, start=1):
            try:
                return await self._stream(sent, out_path, word_boundary=word_boundary)
            except Exception as exc:  # edge-tts ném nhiều loại lỗi mạng/websocket
                last = exc
                log.warning("edge-tts lần %d/%d lỗi: %s", attempt, len(variants), exc)
                if attempt < len(variants):
                    await self._sleep(min(2**attempt, 8))
        raise EdgeTTSError(str(last)) from last

    async def _stream(self, text: str, out_path: Path, word_boundary: bool = True) -> list[Word]:
        comm = (
            edge_tts.Communicate(text, self.voice, boundary="WordBoundary")
            if word_boundary
            else edge_tts.Communicate(text, self.voice)
        )
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
