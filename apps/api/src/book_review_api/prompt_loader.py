"""Loader prompt theo version: file `prompts/<tên>_v<N>.md`, tên đầy đủ có version là khoá.

Mỗi run ghi `prompt_version` (các prompt đang dùng) vào metadata của run LangSmith, xem `agui`.
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Version đang dùng cho từng prompt. Đổi version ở đây (và thêm file mới), không sửa file cũ.
ACTIVE_PROMPTS: dict[str, str] = {
    "research": "research_v1",
    "storyboard": "storyboard_v1",
    "scene_rewrite": "scene_rewrite_instruction_v1",
    "faithfulness_judge": "faithfulness_judge_v1",
    "faithfulness_rewrite": "faithfulness_rewrite_v1",
}


@lru_cache
def load_prompt(version: str) -> str:
    """Đọc `prompts/<version>.md`, ví dụ `load_prompt("storyboard_v1")`."""
    path = PROMPTS_DIR / f"{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Không có prompt {version!r} trong {PROMPTS_DIR}")
    return path.read_text(encoding="utf-8")


def prompt_versions() -> dict[str, str]:
    """Bản sao `ACTIVE_PROMPTS`, dùng làm metadata run."""
    return dict(ACTIVE_PROMPTS)


def prompt_version_label() -> str:
    """Một chuỗi gọn để lọc trên LangSmith, ví dụ `research_v1,storyboard_v1,...`."""
    return ",".join(ACTIVE_PROMPTS.values())
