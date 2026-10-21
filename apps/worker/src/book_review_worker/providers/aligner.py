"""Forced alignment dự phòng khi TTS không trả timestamp từng từ (ADR 0002)."""

import importlib
from pathlib import Path
from typing import Any

from book_review_worker.providers.base import Word

# Khoảng lặng đầu file edge-tts (~0,1 s) và đuôi (~0,8 s): lời đọc nằm giữa hai mốc này.
LEAD_S = 0.1
TAIL_S = 0.8


class ProportionalAligner:
    """Chia thời lượng cho các từ theo số ký tự. Không cần model, sai số cỡ vài trăm ms.

    Đủ để pipeline không dừng; muốn chính xác dùng `StableTsAligner`.
    """

    def align(self, audio_path: Path, text: str, duration_s: float) -> list[Word]:
        tokens = text.split()
        if not tokens:
            return []
        start = min(LEAD_S, duration_s / 4)
        end = max(start, duration_s - TAIL_S) if duration_s > TAIL_S + start else duration_s
        total = sum(len(t) for t in tokens)
        cursor = start
        words: list[Word] = []
        for token in tokens:
            span = (end - start) * len(token) / total
            words.append(Word(text=token, start_s=cursor, end_s=cursor + span))
            cursor += span
        return words


class StableTsAligner:
    """Căn bằng stable-ts (`pip install stable-ts`, tải model Whisper lần đầu)."""

    def __init__(self, model: str = "base", language: str = "vi") -> None:
        stable_whisper: Any = importlib.import_module("stable_whisper")
        self._model: Any = stable_whisper.load_model(model)
        self._language = language

    def align(self, audio_path: Path, text: str, duration_s: float) -> list[Word]:
        result: Any = self._model.align(str(audio_path), text, language=self._language)
        return [
            Word(text=w.word.strip(), start_s=float(w.start), end_s=float(w.end))
            for segment in result.segments
            for w in segment.words
        ]
