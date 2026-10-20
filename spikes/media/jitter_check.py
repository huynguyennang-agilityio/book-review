"""Đo độ rung của một clip Ken Burns trượt ngang đều.

Clip được tạo với tốc độ trượt không đổi, nên dịch chuyển giữa 2 frame liên tiếp
phải gần như bằng nhau. Script ước lượng dịch chuyển bằng phase correlation
(có nội suy parabol để ra số lẻ pixel) rồi in mean, std, và độ lệch lớn nhất
so với trung bình. std càng nhỏ thì càng mượt.

    python spikes/media/jitter_check.py out/kenburns/A_zoompan.mp4
"""

import subprocess
import sys

import numpy as np

W, H = 720, 1280


def read_gray(path: str) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)


WINDOW = np.outer(np.hanning(H), np.hanning(W)).astype(np.float32)


def shift_x(a: np.ndarray, b: np.ndarray) -> float:
    """Dịch chuyển ngang (pixel, có số lẻ) từ a sang b."""
    A = np.fft.fft2((a - a.mean()) * WINDOW)
    B = np.fft.fft2((b - b.mean()) * WINDOW)
    R = A * np.conj(B)
    R /= np.abs(R) + 1e-9
    r = np.real(np.fft.ifft2(R))
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    left, mid, right = r[dy, (dx - 1) % W], r[dy, dx], r[dy, (dx + 1) % W]
    denom = left - 2 * mid + right
    delta = 0.5 * (left - right) / denom if denom != 0 else 0.0
    sx = dx + delta
    return sx - W if sx > W / 2 else sx


def main(path: str) -> None:
    frames = read_gray(path)
    v = np.array([shift_x(frames[i], frames[i + 1]) for i in range(len(frames) - 1)])
    print(f"{path}")
    print(f"  frames      : {len(frames)}")
    print(f"  mean dx/frame: {v.mean():+.3f} px")
    print(f"  std dx/frame : {v.std():.3f} px   (càng nhỏ càng mượt)")
    print(f"  max |dx-mean|: {np.abs(v - v.mean()).max():.3f} px")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Cách dùng: python jitter_check.py <clip.mp4>")
    main(sys.argv[1])
