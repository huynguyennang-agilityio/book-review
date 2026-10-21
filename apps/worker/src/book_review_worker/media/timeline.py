"""Timeline tuyệt đối cho cả video: start/end của từng cảnh, shot và từng từ.

Mọi thời điểm tính từ đầu video. Cảnh nối tiếp nhau, giữa hai cảnh có một khoảng nghỉ
`gap_s`; khoảng nghỉ thuộc về shot cuối của cảnh trước nên hình không bị hở.
"""

import math

from pydantic import BaseModel

from book_review_worker.providers.base import Word

GAP_MIN_S = 0.15
GAP_MAX_S = 0.3
SHOT_MIN_S = 3.0
SHOT_MAX_S = 6.0
SHOT_TARGET_S = 4.5
# Giữ một chút hơi thở sau từ cuối thay vì cắt sát; phần lặng dài hơn (~0,8 s) bị bỏ.
TAIL_KEEP_S = 0.15


class SceneAudio(BaseModel):
    scene_id: int
    audio_path: str
    # Độ dài file audio (ffprobe).
    duration_s: float
    # Thời điểm từ tương đối so với đầu file audio.
    words: list[Word]
    # Số ảnh của cảnh, dùng để xoay vòng `image_ref` giữa các shot.
    image_count: int = 1


class TimelineShot(BaseModel):
    index: int
    image_ref: int
    start_s: float
    end_s: float


class TimelineScene(BaseModel):
    scene_id: int
    audio_path: str
    # Lời đọc của cảnh nằm trong [start_s, end_s]; audio chỉ phát `narration_s` đầu tiên.
    start_s: float
    end_s: float
    narration_s: float
    gap_after_s: float
    words: list[Word]
    shots: list[TimelineShot]


class Timeline(BaseModel):
    scenes: list[TimelineScene]
    total_duration_s: float


def narration_length(audio: SceneAudio) -> float:
    """Độ dài lời đọc: tới từ cuối cộng chút hơi thở, không vượt độ dài file."""
    if not audio.words:
        return audio.duration_s
    return min(audio.duration_s, audio.words[-1].end_s + TAIL_KEEP_S)


def shot_count(span_s: float) -> int:
    """Số shot sao cho mỗi shot dài 3–6 s (cảnh ngắn hơn 3 s chỉ có một shot)."""
    if span_s < SHOT_MIN_S:
        return 1
    low = math.ceil(span_s / SHOT_MAX_S)
    high = math.floor(span_s / SHOT_MIN_S)
    return min(max(round(span_s / SHOT_TARGET_S), low), high)


def build_timeline(audios: list[SceneAudio], gap_s: float = 0.2) -> Timeline:
    if not GAP_MIN_S <= gap_s <= GAP_MAX_S:
        raise ValueError(f"gap_s phải trong [{GAP_MIN_S}, {GAP_MAX_S}], nhận {gap_s}")
    scenes: list[TimelineScene] = []
    cursor = 0.0
    for i, audio in enumerate(audios):
        narration = narration_length(audio)
        gap = gap_s if i < len(audios) - 1 else 0.0
        start = cursor
        end = start + narration
        span = narration + gap
        n = shot_count(span)
        shots = [
            TimelineShot(
                index=k,
                image_ref=k % max(audio.image_count, 1),
                start_s=start + span * k / n,
                # Shot cuối lấy đúng mốc cuối để không tích luỹ sai số làm tròn.
                end_s=start + span * (k + 1) / n if k < n - 1 else start + span,
            )
            for k in range(n)
        ]
        scenes.append(
            TimelineScene(
                scene_id=audio.scene_id,
                audio_path=audio.audio_path,
                start_s=start,
                end_s=end,
                narration_s=narration,
                gap_after_s=gap,
                words=[
                    Word(text=w.text, start_s=start + w.start_s, end_s=start + w.end_s)
                    for w in audio.words
                ],
                shots=shots,
            )
        )
        cursor = end + gap
    return Timeline(scenes=scenes, total_duration_s=cursor)
