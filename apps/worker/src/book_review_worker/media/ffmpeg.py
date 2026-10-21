"""Gọi ffmpeg/ffprobe: dựng clip Ken Burns, ghép xfade, đặt audio theo offset, burn phụ đề."""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from book_review_worker.media.kenburns import FPS, H, W, kenburns_filter
from book_review_worker.media.placeholder import find_font, wrap
from book_review_worker.media.subtitles import FONT_SIZE, POSITION_RATIO, SubtitleCue
from book_review_worker.media.timeline import Timeline

XFADE_S = 0.2


def run_ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {proc.stderr[-800:]}")


def probe_duration(path: Path) -> float:
    """Thời lượng file media (giây) theo ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return float(out.strip())


def render_clip(image: Path, duration_s: float, direction: str, out: Path) -> None:
    """Một shot: ảnh + Ken Burns thành mp4 không tiếng, đúng `duration_s` giây."""
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = round(duration_s * FPS)
    run_ffmpeg(
        [
            *("-loop", "1", "-framerate", str(FPS), "-i", str(image)),
            *("-vf", kenburns_filter(duration_s, direction)),
            *("-frames:v", str(frames)),
            *("-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast"),
            str(out),
        ]
    )


def concat_xfade(clips: list[Path], starts: list[float], ends: list[float], out: Path) -> None:
    """Ghép clip bằng xfade. Mỗi clip (trừ cuối) được kéo dài thêm XFADE_S để bù phần chồng, nên
    shot k bắt đầu đúng `starts[k]` và tổng thời lượng bằng `ends[-1]`.

    Clip phải render dài `end - start + XFADE_S` giây (trừ clip cuối)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(clips) == 1:
        out.write_bytes(clips[0].read_bytes())
        return
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    chain: list[str] = []
    prev = "0:v"
    for k in range(1, len(clips)):
        label = f"v{k}"
        chain.append(
            f"[{prev}][{k}:v]xfade=transition=fade:duration={XFADE_S}:offset={starts[k]:.3f}[{label}]"
        )
        prev = label
    run_ffmpeg(
        [
            *inputs,
            *("-filter_complex", ";".join(chain), "-map", f"[{prev}]"),
            *("-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast"),
            str(out),
        ]
    )


def render_subtitle_pngs(cues: list[SubtitleCue], out_dir: Path, total_s: float) -> Path:
    """Dựng danh sách ảnh PNG trong suốt (concat demuxer) phủ kín `total_s` giây."""
    out_dir.mkdir(parents=True, exist_ok=True)
    font = find_font(FONT_SIZE)
    blank = out_dir / "blank.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    lines: list[str] = ["ffconcat version 1.0"]
    cursor = 0.0

    def add(path: Path, dur: float) -> None:
        if dur > 1e-6:
            lines.append(f"file '{path.resolve().as_posix()}'")
            lines.append(f"duration {dur:.4f}")

    for i, cue in enumerate(cues):
        start = max(cue.start_s, cursor)
        add(blank, start - cursor)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        rows = wrap(cue.text, draw, font, W - 80)
        y = int(H * POSITION_RATIO) - len(rows) * FONT_SIZE // 2
        for row in rows:
            x = (W - draw.textlength(row, font=font)) / 2
            draw.text(
                (x, y),
                row,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=3,
                stroke_fill=(0, 0, 0, 255),
            )
            y += int(FONT_SIZE * 1.25)
        png = out_dir / f"cue_{i:04d}.png"
        img.save(png)
        add(png, max(cue.end_s - start, 0.04))
        cursor = max(cue.end_s, start + 0.04)
    add(blank, total_s - cursor + 1.0)
    # concat demuxer cần lặp file cuối để duration cuối có hiệu lực.
    lines.append(lines[-2])
    listing = out_dir / "subs.ffconcat"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing


def compose_final(
    video: Path,
    timeline: Timeline,
    media_dir: Path,
    subs_listing: Path,
    out: Path,
) -> None:
    """Pass cuối: đặt audio từng cảnh theo offset tuyệt đối, burn phụ đề, mux ra mp4."""
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = ["-i", str(video)]
    for scene in timeline.scenes:
        inputs += ["-i", str(media_dir / scene.audio_path)]
    inputs += ["-f", "concat", "-safe", "0", "-i", str(subs_listing)]
    sub_idx = len(timeline.scenes) + 1
    parts: list[str] = []
    labels: list[str] = []
    for i, scene in enumerate(timeline.scenes, 1):
        ms = round(scene.start_s * 1000)
        parts.append(
            f"[{i}:a]atrim=0:{scene.narration_s:.3f},asetpts=PTS-STARTPTS,"
            f"adelay={ms}|{ms},aresample=44100[a{i}]"
        )
        labels.append(f"[a{i}]")
    parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
        f"apad=whole_dur={timeline.total_duration_s:.3f}[aout]"
    )
    parts.append(f"[{sub_idx}:v]fps={FPS},format=rgba[subs]")
    parts.append("[0:v][subs]overlay=format=auto:shortest=0,format=yuv420p[vout]")
    run_ffmpeg(
        [
            *inputs,
            *("-filter_complex", ";".join(parts)),
            *("-map", "[vout]", "-map", "[aout]"),
            *("-t", f"{timeline.total_duration_s:.3f}"),
            *("-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast"),
            *("-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"),
            str(out),
        ]
    )
