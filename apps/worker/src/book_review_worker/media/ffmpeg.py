"""Gọi ffmpeg/ffprobe. Phần ghép cảnh (xfade, burn phụ đề) thêm ở ngày 13."""

import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    """Thời lượng file media (giây) theo ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return float(out.strip())
