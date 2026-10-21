"""Ken Burns bằng phóng 2× rồi crop theo frame (ADR 0001), xuất 720×1280@30fps."""

from collections.abc import Sequence

W, H, FPS = 720, 1280, 30
ZOOM = 1.25
# Xoay vòng hướng pan để các shot liền nhau không chuyển động giống hệt.
DIRECTIONS: Sequence[str] = ("right", "left", "down", "up")


def kenburns_filter(duration_s: float, direction: str = "right") -> str:
    """Chuỗi filter FFmpeg cho một ảnh đã được lặp thành `duration_s` giây ở 30fps."""
    last = max(round(duration_s * FPS) - 1, 1)
    big_w, big_h = W * 3, H * 3  # 2160×3840 như ADR; crop cửa sổ 1/ZOOM rồi thu về 720×1280
    crop_w = round(big_w / ZOOM / 2) * 2
    crop_h = round(big_h / ZOOM / 2) * 2
    progress = f"n/{last}"
    xs = {
        "right": f"(iw-{crop_w})*{progress}",
        "left": f"(iw-{crop_w})*(1-{progress})",
    }
    ys = {
        "down": f"(ih-{crop_h})*{progress}",
        "up": f"(ih-{crop_h})*(1-{progress})",
    }
    x = xs.get(direction, f"(iw-{crop_w})/2")
    y = ys.get(direction, f"(ih-{crop_h})/2")
    return (
        f"scale={big_w}:{big_h},crop=w={crop_w}:h={crop_h}:x='{x}':y='{y}',"
        f"scale={W}:{H},setsar=1,fps={FPS},format=yuv420p"
    )
