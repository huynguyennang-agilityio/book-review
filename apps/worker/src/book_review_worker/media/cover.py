"""Ảnh bìa `cover.jpg` 720×1280: khung hình đầu của video + tên sách và hook trong safe zone."""

from pathlib import Path

from PIL import Image, ImageDraw

from book_review_worker.media.ffmpeg import run_ffmpeg
from book_review_worker.media.kenburns import H, W
from book_review_worker.media.overlay import CENTER_X, SAFE_Y0, SAFE_Y1, TEXT_WIDTH
from book_review_worker.media.placeholder import find_font, wrap

TITLE_SIZE = 76
SUBTITLE_SIZE = 44


def _centered(draw: ImageDraw.ImageDraw, rows: list[str], y: int, size: int, fill: tuple) -> int:  # type: ignore[type-arg]
    font = find_font(size)
    for row in rows:
        x = CENTER_X - draw.textlength(row, font=font) / 2
        draw.text((x, y), row, font=font, fill=fill, stroke_width=4, stroke_fill=(0, 0, 0))
        y += int(size * 1.2)
    return y


def make_cover(video: Path, title: str, hook: str, out: Path, at_s: float = 1.0) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    frame = out.with_suffix(".frame.png")
    run_ffmpeg(["-ss", f"{at_s:.2f}", "-i", str(video), "-frames:v", "1", str(frame)])
    img = Image.open(frame).convert("RGB").resize((W, H))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle([0, SAFE_Y0, W, SAFE_Y1], fill=(0, 0, 0, 110))
    img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(img)
    title_rows = wrap(title, draw, find_font(TITLE_SIZE), TEXT_WIDTH)[:3]
    hook_rows = wrap(hook, draw, find_font(SUBTITLE_SIZE), TEXT_WIDTH)[:4] if hook else []
    block = int(len(title_rows) * TITLE_SIZE * 1.2 + 30 + len(hook_rows) * SUBTITLE_SIZE * 1.2)
    y = max(SAFE_Y0 + 20, (SAFE_Y0 + SAFE_Y1 - block) // 2)
    y = _centered(draw, title_rows, y, TITLE_SIZE, (255, 214, 10))
    _centered(draw, hook_rows, y + 30, SUBTITLE_SIZE, (255, 255, 255))
    img.save(out, quality=90)
    frame.unlink(missing_ok=True)
