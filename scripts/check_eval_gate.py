"""Chặn merge khi faithfulness trung bình của báo cáo eval dưới ngưỡng.

uv run python scripts/check_eval_gate.py [docs/evals/eval_report.json] [--min 0.9]
"""

import argparse
import json
import sys
from pathlib import Path


def check(report: dict[str, object], minimum: float) -> tuple[bool, str]:
    summary = report["summary"]
    assert isinstance(summary, dict)
    block = summary["context_body"]
    score = min(block.get("vi_final", block["vi"]), block.get("ragas_final") or 1.0)
    failed = report.get("books_failed") or []
    ok = score >= minimum and not failed
    return ok, f"faithfulness context/body = {score:.3f} (ngưỡng {minimum}), sách lỗi: {failed}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="docs/evals/eval_report.json")
    parser.add_argument("--min", type=float, default=0.9, dest="minimum")
    args = parser.parse_args()
    ok, message = check(json.loads(Path(args.report).read_text(encoding="utf-8")), args.minimum)
    print(message)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
