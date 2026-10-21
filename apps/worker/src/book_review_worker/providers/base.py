"""Interface TTS và aligner, cùng kiểu dữ liệu từ-theo-thời-gian dùng chung."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class Word(BaseModel):
    text: str
    start_s: float
    end_s: float


class TTSResult(BaseModel):
    audio_path: str
    # Độ dài file đo bằng ffprobe (gồm cả khoảng lặng cuối), không suy từ offset từ cuối.
    duration_s: float
    words: list[Word]


class TTSProvider(Protocol):
    async def synthesize(self, text: str, out_path: Path) -> TTSResult: ...


class Aligner(Protocol):
    """Gán thời điểm từng từ khi nhà cung cấp TTS không trả WordBoundary."""

    def align(self, audio_path: Path, text: str, duration_s: float) -> list[Word]: ...
