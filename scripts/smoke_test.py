"""Smoke test: dựng 1 video ngắn (1 cảnh) qua worker arq với provider giả lập (ảnh placeholder).

    uv run python scripts/smoke_test.py            # cần Redis + worker, MEDIA_DIR dùng chung
    SMOKE_API_URL=https://staging.example.com uv run python scripts/smoke_test.py

Có SMOKE_API_URL thì gọi thêm GET /health. Thoát mã 0 nếu ra mp4 có thời lượng > 0.
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_health(url: str) -> None:
    with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=15) as resp:  # noqa: S310
        if resp.status != 200:
            sys.exit(f"/health trả {resp.status}")
    print(f"health ok: {url}")


def main() -> None:
    api_url = os.environ.get("SMOKE_API_URL")
    if api_url:
        check_health(api_url)
    storyboard = {
        "book": {"title": "Smoke test"},
        "book_category": "non_fiction",
        "spoiler_free": True,
        "hook_vi": "",
        "style_prompt_en": "",
        "caption_vi": "",
        "scenes": [
            {
                "id": 1,
                "section": "body",
                "narration_vi": "Đây là video kiểm tra nhanh của hệ thống.",
                "scene_type": "title",
                "mood": "warm",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "storyboard.json"
        path.write_text(json.dumps(storyboard, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(  # noqa: S603
            [sys.executable, str(ROOT / "scripts" / "run_media.py"), str(path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    print(proc.stdout)
    if proc.returncode != 0:
        sys.exit(f"run_media lỗi:\n{proc.stderr[-2000:]}")
    line = next((x for x in proc.stdout.splitlines() if x.startswith("video ")), "")
    if not line or float(line.split()[1].rstrip("s")) <= 0:
        sys.exit("không có video hợp lệ")
    print("smoke test OK")


if __name__ == "__main__":
    main()
