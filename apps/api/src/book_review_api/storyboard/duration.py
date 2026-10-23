"""Ước lượng thời lượng đọc của lời thoại tiếng Việt (edge-tts), để kiểm độ dài kịch bản trước TTS.

Hệ số đo ở spike ngày 1 (`docs/spikes/day-01-media.md`): 67-72 âm tiết đọc trong 16,8-18,9 giây
với cả hai giọng, tức ~3,8 âm tiết/giây. Mỗi cảnh cộng thêm phần lặng đầu file (~0,1 s), hơi thở
worker giữ lại sau từ cuối (`TAIL_KEEP_S` = 0,15 s) và khoảng nghỉ giữa hai cảnh (`scene_gap_s`).
"""

import re
from collections.abc import Iterable

SYLLABLES_PER_S = 3.8
SCENE_OVERHEAD_S = 0.45

_SYLLABLE_RE = re.compile(r"\w+")


def count_syllables(text: str) -> int:
    """Tiếng Việt viết tách âm tiết bằng khoảng trắng nên mỗi cụm chữ/số là một âm tiết."""
    return len(_SYLLABLE_RE.findall(text))


def scene_seconds(narration: str) -> float:
    return count_syllables(narration) / SYLLABLES_PER_S + SCENE_OVERHEAD_S


def estimate_seconds(narrations: Iterable[str]) -> float:
    return sum(scene_seconds(n) for n in narrations)


def syllables_for(seconds: float) -> int:
    """Số âm tiết cần cho một cảnh dài `seconds` giây."""
    return max(1, round((seconds - SCENE_OVERHEAD_S) * SYLLABLES_PER_S))
