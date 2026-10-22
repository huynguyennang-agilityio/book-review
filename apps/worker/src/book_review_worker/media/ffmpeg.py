"""Gọi ffmpeg/ffprobe: dựng clip Ken Burns, ghép xfade, đặt audio theo offset, burn phụ đề."""

import subprocess
from pathlib import Path

from book_review_worker.media.kenburns import FPS, kenburns_filter
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


def burn_overlay(video: Path, listing: Path, total_s: float, out: Path) -> None:
    """Pass cuối phần hình: phủ chuỗi PNG (phụ đề + chữ nổi bật), xuất mp4 không tiếng."""
    out.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            *("-i", str(video)),
            *("-f", "concat", "-safe", "0", "-i", str(listing)),
            *("-filter_complex", f"[1:v]fps={FPS},format=rgba[ov];"
              "[0:v][ov]overlay=format=auto:shortest=0,format=yuv420p[vout]"),
            *("-map", "[vout]", "-t", f"{total_s:.3f}"),
            *("-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast"),
            str(out),
        ]
    )  # fmt: skip


MUSIC_VOLUME = 0.45
DUCK_FILTER = "sidechaincompress=threshold=0.02:ratio=10:attack=20:release=600"
# Hợp âm La thứ (A2, A3, C4, E4) làm nền ambient; tự tổng hợp nên không vướng bản quyền.
_CHORD_HZ = (110.0, 220.0, 261.63, 329.63)


def make_music(path: Path, duration_s: float) -> Path:
    """Nhạc nền ambient tổng hợp bằng ffmpeg (royalty-free vì tự tạo), dài `duration_s` giây."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    for hz in _CHORD_HZ:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={hz}:duration={duration_s:.2f}"]
    fade = min(2.0, duration_s / 4)
    graph = (
        f"amix=inputs={len(_CHORD_HZ)}:normalize=0,lowpass=f=900,"
        f"tremolo=f=0.2:d=0.5,volume=0.5,afade=t=in:d={fade:.2f},"
        f"afade=t=out:st={duration_s - fade:.2f}:d={fade:.2f},aformat=channel_layouts=stereo"
    )
    run_ffmpeg([*inputs, *("-filter_complex", graph), *("-c:a", "aac", "-b:a", "96k"), str(path)])
    return path


def mux_audio(
    video: Path, timeline: Timeline, media_dir: Path, out: Path, music: Path | None = None
) -> None:
    """Đặt audio từng cảnh theo offset tuyệt đối rồi mux vào video (không encode lại hình).

    Có `music` thì trộn nhạc nền, nhạc được hạ xuống khi có lời đọc (sidechaincompress)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = ["-i", str(video)]
    for scene in timeline.scenes:
        inputs += ["-i", str(media_dir / scene.audio_path)]
    parts: list[str] = []
    labels: list[str] = []
    for i, scene in enumerate(timeline.scenes, 1):
        ms = round(scene.start_s * 1000)
        parts.append(
            f"[{i}:a]atrim=0:{scene.narration_s:.3f},asetpts=PTS-STARTPTS,"
            f"adelay={ms}|{ms},aresample=44100[a{i}]"
        )
        labels.append(f"[a{i}]")
    total = timeline.total_duration_s
    voice = (
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
        f"apad=whole_dur={total:.3f},atrim=0:{total:.3f}"
    )
    if music is None:
        parts.append(f"{voice}[aout]")
    else:
        inputs += ["-i", str(music)]
        m = len(timeline.scenes) + 1
        parts.append(f"{voice},aformat=channel_layouts=stereo,asplit=2[vs][vm]")
        parts.append(f"[{m}:a]aresample=44100,volume={MUSIC_VOLUME},apad,atrim=0:{total:.3f}[mq]")
        parts.append(f"[mq][vm]{DUCK_FILTER}[duck]")
        parts.append("[vs][duck]amix=inputs=2:normalize=0:duration=first[aout]")
    run_ffmpeg(
        [
            *inputs,
            *("-filter_complex", ";".join(parts)),
            *("-map", "0:v", "-map", "[aout]"),
            *("-t", f"{total:.3f}"),
            *("-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"),
            str(out),
        ]
    )
