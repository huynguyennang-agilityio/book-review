"""Lớp phủ chữ (phụ đề + chữ nổi bật) thành chuỗi PNG trong suốt cho concat demuxer.

Bản FFmpeg trên Mac không có libass/drawtext nên chữ được vẽ bằng Pillow. Mọi chữ nằm trong safe
zone (trên 15%, dưới 20%, mép phải 12%). Karaoke: mỗi từ được tô sáng đúng lúc nó được đọc.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from book_review_worker.media.kenburns import H, W
from book_review_worker.media.placeholder import find_font, wrap
from book_review_worker.media.subtitles import (
    FONT_SIZE,
    POSITION_RATIO,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
    SAFE_TOP,
    SubtitleCue,
)

HIGHLIGHT_SIZE = 64
HIGHLIGHT_TOP_RATIO = 0.19
HIGHLIGHT_MAX_ROWS = 4
KARAOKE_COLOR = (255, 214, 10, 255)
TEXT_COLOR = (255, 255, 255, 255)
STROKE = (0, 0, 0, 255)

LEFT_PX = round(W * SAFE_LEFT)
RIGHT_PX = round(W * SAFE_RIGHT)
TEXT_WIDTH = W - LEFT_PX - RIGHT_PX
CENTER_X = LEFT_PX + TEXT_WIDTH / 2
SAFE_Y0 = round(H * SAFE_TOP)
SAFE_Y1 = round(H * (1 - SAFE_BOTTOM))


class Highlight(BaseModel):
    """Chữ nổi bật (hook, chữ trên màn hình của cảnh) hiện từ start_s tới end_s."""

    text: str
    start_s: float
    end_s: float


Font = ImageFont.FreeTypeFont | ImageFont.ImageFont
Color = tuple[int, int, int, int]


def _draw_row(
    draw: ImageDraw.ImageDraw, row: str, y: int, f: Font, fills: list[Color] | None
) -> None:
    """Vẽ một dòng căn giữa trong vùng an toàn; `fills` là màu từng từ (karaoke) hoặc None."""
    total = draw.textlength(row, font=f)
    x = CENTER_X - total / 2
    if fills is None:
        draw.text((x, y), row, font=f, fill=TEXT_COLOR, stroke_width=3, stroke_fill=STROKE)
        return
    space = draw.textlength(" ", font=f)
    for word, fill in zip(row.split(), fills, strict=True):
        draw.text((x, y), word, font=f, fill=fill, stroke_width=3, stroke_fill=STROKE)
        x += draw.textlength(word, font=f) + space


def render_frame(
    cue: SubtitleCue | None, active: int | None, highlight: str | None, karaoke: bool
) -> Image.Image:
    """Một khung lớp phủ. `active` là chỉ số từ đang đọc trong cue (karaoke)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if highlight:
        font = find_font(HIGHLIGHT_SIZE)
        rows = wrap(highlight, draw, font, TEXT_WIDTH)[:HIGHLIGHT_MAX_ROWS]
        y = round(H * HIGHLIGHT_TOP_RATIO)
        for row in rows:
            _draw_row(draw, row, y, font, None)
            y += int(HIGHLIGHT_SIZE * 1.2)
    if cue is not None:
        font = find_font(FONT_SIZE)
        rows = wrap(cue.text, draw, font, TEXT_WIDTH)
        y = int(H * POSITION_RATIO) - len(rows) * FONT_SIZE // 2
        index = 0
        for row in rows:
            n = len(row.split())
            fills = None
            if karaoke and active is not None:
                fills = [KARAOKE_COLOR if index + k <= active else TEXT_COLOR for k in range(n)]
            _draw_row(draw, row, y, font, fills)
            index += n
            y += int(FONT_SIZE * 1.25)
    return img


def _events(
    cues: list[SubtitleCue], highlights: list[Highlight], karaoke: bool
) -> list[tuple[float, float, SubtitleCue | None, int | None, str | None]]:
    """Cắt trục thời gian thành các đoạn có cùng trạng thái hiển thị."""
    cuts = {0.0}
    for c in cues:
        cuts.update((c.start_s, c.end_s))
        if karaoke:
            cuts.update(w[1] for w in c.words)
    for h in highlights:
        cuts.update((h.start_s, h.end_s))
    points = sorted(cuts)
    out: list[tuple[float, float, SubtitleCue | None, int | None, str | None]] = []
    for a, b in zip(points, points[1:], strict=False):
        if b - a < 1e-6:
            continue
        mid = (a + b) / 2
        cue = next((c for c in cues if c.start_s <= mid < c.end_s), None)
        active = None
        if cue is not None and karaoke:
            started = [i for i, w in enumerate(cue.words) if w[1] <= mid]
            active = started[-1] if started else None
        hl = next((h.text for h in highlights if h.start_s <= mid < h.end_s), None)
        out.append((a, b, cue, active, hl))
    return out


def render_overlay_track(
    cues: list[SubtitleCue],
    highlights: list[Highlight],
    out_dir: Path,
    total_s: float,
    karaoke: bool = False,
) -> Path:
    """Ghi các PNG và `overlay.ffconcat` phủ kín `total_s` giây."""
    out_dir.mkdir(parents=True, exist_ok=True)
    blank = out_dir / "blank.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    lines: list[str] = ["ffconcat version 1.0"]
    cursor = 0.0
    cache: dict[tuple[str, int | None, str | None], Path] = {}

    def add(path: Path, dur: float) -> None:
        if dur > 1e-6:
            lines.append(f"file '{path.resolve().as_posix()}'")
            lines.append(f"duration {dur:.4f}")

    for a, b, cue, active, hl in _events(cues, highlights, karaoke):
        add(blank, a - cursor)
        if cue is None and hl is None:
            add(blank, b - a)
        else:
            key = (cue.text if cue else "", active, hl)
            png = cache.get(key)
            if png is None:
                png = out_dir / f"frame_{len(cache):05d}.png"
                render_frame(cue, active, hl, karaoke).save(png)
                cache[key] = png
            add(png, b - a)
        cursor = b
    add(blank, total_s - cursor + 1.0)
    # concat demuxer cần lặp file cuối để duration cuối có hiệu lực.
    lines.append(lines[-2])
    listing = out_dir / "overlay.ffconcat"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing
