"""Chạy thật tab "Từ bài review có sẵn" tới hết storyboard: chia cảnh nguyên văn + metadata Gemini.

    uv run python scripts/run_review_text.py evals/review-text/nha-gia-kim.md --title "Nhà giả kim"

File `.md` có tiêu đề `## Hook`, `## Ý chính`, `## Nhận xét` thì tách vào 3 ô, không thì cả file
là Ý chính. Cần GOOGLE_API_KEY trong .env. Không nạp RAG (không cần DB). In số cảnh, thời lượng
ước tính và chi phí; `--json` in cả storyboard.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from book_review_api.config import get_settings
from book_review_api.graph.nodes.precheck import fold, precheck
from book_review_api.graph.nodes.review_text import make_ingest_review_node
from book_review_api.providers.llm_gemini import make_gemini_with_fallback
from book_review_api.storyboard.review_meta import make_meta_writer
from book_review_api.storyboard.schema import Storyboard

HEADINGS = {"hook": "hook", "y chinh": "main", "nhan xet": "comment"}
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def split_fields(text: str) -> dict[str, str]:
    """`## Hook` / `## Ý chính` / `## Nhận xét` -> 3 ô; không có tiêu đề thì cả bài là Ý chính."""
    marks = [(m, HEADINGS.get(fold(m.group(1)))) for m in _HEADING_RE.finditer(text)]
    marks = [(m, f) for m, f in marks if f]
    if not marks:
        return {"main": text}
    out: dict[str, str] = {}
    for k, (m, field) in enumerate(marks):
        end = marks[k + 1][0].start() if k + 1 < len(marks) else len(text)
        out[field] = text[m.end() : end].strip()
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--title", help="Tên sách (mặc định lấy từ tên file)")
    parser.add_argument("--json", action="store_true", help="In cả storyboard")
    args = parser.parse_args()
    settings = get_settings()
    node = make_ingest_review_node(
        make_meta_writer(make_gemini_with_fallback(settings)), settings=settings
    )
    for path in args.files:
        title = args.title or path.stem.replace("-", " ").capitalize()
        state: dict[str, Any] = {
            "book": {"title": title},
            "options": {"source": "user_review"},
            "user_review": split_fields(path.read_text(encoding="utf-8")),
        }
        print(f"\n=== {path.name} ({title})")
        checked = precheck(state)  # type: ignore[arg-type]
        if checked.get("status") == "rejected":
            print("BỊ CHẶN:", checked.get("error_code"))
            continue
        out = node({**state, **checked})  # type: ignore[arg-type]
        if "storyboard" not in out:
            print("THẤT BẠI:", out.get("status"), out.get("error_code"))
            continue
        sb = Storyboard.model_validate(out["storyboard"])
        if args.json:
            print(json.dumps(out["storyboard"], ensure_ascii=False, indent=2))
        by_section = {
            s: sum(x.section == s for x in sb.scenes) for s in ("hook", "body", "review_cta")
        }
        seconds = sb.estimated_seconds or 0
        cost = out.get("cost") or {}
        length = f"{seconds // 60:.0f}:{seconds % 60:02.0f}"
        print(
            f"{len(sb.scenes)} cảnh {by_section}, ước tính ~{length}"
            f", loại {sb.book_category}, nhân vật {[c.name for c in sb.characters]}"
        )
        print(f"cờ: {sb.flags or 'không'}, chi phí Gemini: ${cost.get('usd', 0):.5f}")
        for s in sb.scenes[:4]:
            print(f"  [{s.id} {s.section}/{s.scene_type}/{s.mood}] {s.on_screen_text_vi!r}")


if __name__ == "__main__":
    main()
