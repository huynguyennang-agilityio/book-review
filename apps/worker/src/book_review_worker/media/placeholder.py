"""Ảnh placeholder (màu theo mood + chữ) cho mỗi shot, thay bằng ảnh thật ở các ngày sau."""

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
)
# Nền không bao giờ đen: mỗi mood một màu sáng vừa phải.
MOOD_COLORS: dict[str, tuple[int, int, int]] = {
    "warm": (196, 120, 60),
    "tense": (140, 50, 60),
    "calm": (60, 120, 150),
    "hopeful": (70, 140, 90),
    "dark": (70, 60, 110),
}
SIZE = (1080, 1920)


def find_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def mood_color(mood: str) -> tuple[int, int, int]:
    if mood in MOOD_COLORS:
        return MOOD_COLORS[mood]
    h = hashlib.sha1(mood.encode()).digest()
    return (60 + h[0] % 140, 60 + h[1] % 140, 60 + h[2] % 140)


def wrap(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width: int,
) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def make_placeholder(path: Path, label: str, mood: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    r, g, b = mood_color(mood)
    img = Image.new("RGB", SIZE, (r, g, b))
    draw = ImageDraw.Draw(img)
    # Dải sáng dần xuống để Ken Burns có chi tiết nhìn thấy được chuyển động.
    for y in range(0, SIZE[1], 8):
        k = y / SIZE[1]
        fill = tuple(int(c + (255 - c) * k * 0.4) for c in (r, g, b))
        draw.rectangle([0, y, SIZE[0], y + 8], fill=fill)
    font = find_font(72)
    lines = wrap(label, draw, font, SIZE[0] - 200)[:8]
    total = len(lines) * 96
    y = (SIZE[1] - total) // 2 - 250
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((SIZE[0] - w) / 2, y), line, font=font, fill=(255, 255, 255))
        y += 96
    img.save(path)
