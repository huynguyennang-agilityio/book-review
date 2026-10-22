"""Phụ đề theo thời gian tuyệt đối: gom từ thành cụm 20–25 ký tự, xuất `.ass` và `.srt`.

Phần burn vào video dùng ảnh PNG do `ffmpeg.py` ghép (xem `render_subtitle_pngs`) vì bản FFmpeg
trên Mac không có libass; `.ass` vẫn xuất ra để dùng với bản có libass hoặc để chỉnh tay.
"""

from pathlib import Path

from pydantic import BaseModel

from book_review_worker.media.timeline import Timeline

CHUNK_MIN_CHARS = 20
CHUNK_MAX_CHARS = 25
WIDTH = 720
HEIGHT = 1280
# Dòng phụ đề nằm ở 65% chiều cao (giữa khoảng 60–70%).
POSITION_RATIO = 0.65
FONT_SIZE = 46
# Safe zone của TikTok/Shorts/Reels (mục 1 plan): chừa phần giao diện nền tảng đè lên.
SAFE_TOP = 0.15
SAFE_BOTTOM = 0.20
SAFE_RIGHT = 0.12
SAFE_LEFT = 0.05


class SubtitleCue(BaseModel):
    text: str
    start_s: float
    end_s: float
    # (từ, start, end) theo thời gian tuyệt đối, dùng cho karaoke.
    words: list[tuple[str, float, float]] = []


def chunk_words(words: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Gom (từ, start, end) thành cụm dài 20–25 ký tự; từ dài hơn mức tối đa đứng riêng một cụm."""
    chunks: list[tuple[str, float, float]] = []
    text = ""
    start = end = 0.0
    for word, w_start, w_end in words:
        candidate = f"{text} {word}" if text else word
        if text and len(candidate) > CHUNK_MAX_CHARS:
            chunks.append((text, start, end))
            text, start = word, w_start
        else:
            if not text:
                start = w_start
            text = candidate
        end = w_end
        if len(text) >= CHUNK_MIN_CHARS:
            chunks.append((text, start, end))
            text = ""
    if text:
        chunks.append((text, start, end))
    return chunks


def build_cues(timeline: Timeline) -> list[SubtitleCue]:
    """Cụm phụ đề cho cả video. Mỗi cụm hiện tới khi cụm kế bắt đầu (cùng cảnh) hoặc hết cảnh."""
    cues: list[SubtitleCue] = []
    for scene in timeline.scenes:
        words = [(w.text, w.start_s, w.end_s) for w in scene.words]
        chunks = chunk_words(words)
        used = 0
        for i, (text, start, end) in enumerate(chunks):
            nxt = chunks[i + 1][1] if i + 1 < len(chunks) else scene.end_s
            n = len(text.split())
            cues.append(
                SubtitleCue(
                    text=text,
                    start_s=start,
                    end_s=max(min(nxt, scene.end_s), end),
                    words=words[used : used + n],
                )
            )
            used += n
    return cues


def _ass_time(t: float) -> str:
    cs = round(t * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _karaoke_text(cue: SubtitleCue) -> str:
    """Văn bản `.ass` có `\\k` (centi-giây) cho từng từ; thiếu word timing thì để nguyên."""
    if not cue.words:
        return cue.text
    parts: list[str] = []
    cursor = cue.start_s
    for word, start, end in cue.words:
        lead = max(start - cursor, 0.0)
        cs = round((end - start + lead) * 100)
        parts.append(f"{{\\k{cs}}}{word}")
        cursor = end
    return " ".join(parts)


def render_ass(cues: list[SubtitleCue], font: str = "Arial", karaoke: bool = False) -> str:
    margin_v = round(HEIGHT * (1 - POSITION_RATIO))
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {WIDTH}\nPlayResY: {HEIGHT}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,3,1,2,40,40,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [
        f"Dialogue: 0,{_ass_time(c.start_s)},{_ass_time(c.end_s)},Default,,0,0,0,,"
        f"{_karaoke_text(c) if karaoke else c.text}"
        for c in cues
    ]
    return header + "\n".join(lines) + "\n"


def render_srt(cues: list[SubtitleCue]) -> str:
    return "\n".join(
        f"{i}\n{_srt_time(c.start_s)} --> {_srt_time(c.end_s)}\n{c.text}\n"
        for i, c in enumerate(cues, 1)
    )


def write_subtitles(
    timeline: Timeline, out_dir: Path, karaoke: bool = False
) -> tuple[Path, Path, list[SubtitleCue]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cues = build_cues(timeline)
    ass = out_dir / "subtitles.ass"
    srt = out_dir / "subtitles.srt"
    ass.write_text(render_ass(cues, karaoke=karaoke), encoding="utf-8")
    srt.write_text(render_srt(cues), encoding="utf-8")
    return ass, srt, cues
