"""Eval faithfulness trên dataset golden: RAGAS gốc và bộ chấm tiếng Việt của pipeline.

    uv run --group eval python evals/run_ragas.py                 # cả 20 sách
    uv run --group eval python evals/run_ragas.py nha-gia-kim     # một vài slug
    uv run --group eval python evals/run_ragas.py --no-ragas      # chỉ bộ chấm tiếng Việt

Cần GOOGLE_API_KEY trong .env. Mỗi sách:
1. Viết storyboard bằng `GEMINI_MODEL` (nguồn cố định trong `evals/golden/<slug>/sources`).
2. Chấm từng cảnh bằng giám khảo `JUDGE_MODEL` (model khác): RAGAS `Faithfulness` và
   `FaithfulnessChecker.judge`. Nguồn của cảnh context/body là các chunk cảnh trích dẫn; hook và
   review_cta không có trích dẫn nên đối chiếu với toàn bộ nguồn của sách và tính riêng.
3. Chạy vòng viết lại của node `faithfulness_eval` cho cảnh context/body dưới ngưỡng, chấm lại.

Kết quả trung gian cache ở `evals/out/<slug>/` (chạy lại không gọi lại model), báo cáo ghi ra
`docs/evals/eval_report.json`. Điểm chấm tay ở `evals/manual/grades.json` được đối chiếu nếu có.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
import types
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from langchain_core.language_models import BaseChatModel

from book_review_api.config import Settings, get_settings
from book_review_api.providers.llm_gemini import make_chat_model, make_embeddings, make_judge_model
from book_review_api.rag.golden import GoldenBook, load_golden
from book_review_api.rag.memory import InMemoryRetriever
from book_review_api.storyboard.faithfulness import (
    JUDGE_PROMPT_VERSION,
    REWRITE_PROMPT_VERSION,
    FaithfulnessChecker,
    Judgement,
    scene_contexts,
)
from book_review_api.storyboard.runner import make_storyboard_runner
from book_review_api.storyboard.schema import CITED_SECTIONS, SECTION_ORDER, Scene, Storyboard

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden"
OUT = ROOT / "evals" / "out"
REPORT = ROOT / "docs" / "evals" / "eval_report.json"
GRADES = ROOT / "evals" / "manual" / "grades.json"


def _shim_vertexai() -> None:
    """ragas 0.4.3 import `ChatVertexAI`/`VertexAI` từ langchain_community, bản mới đã bỏ.

    Hai lớp này chỉ dùng để kiểm tra kiểu, nên đặt lớp rỗng để import được.
    """
    for name, cls in (
        ("langchain_community.chat_models.vertexai", "ChatVertexAI"),
        ("langchain_community.llms.vertexai", "VertexAI"),
    ):
        if name not in sys.modules:
            module = types.ModuleType(name)
            setattr(module, cls, type(cls, (), {}))
            sys.modules[name] = module


class RagasScorer:
    """RAGAS Faithfulness gốc (prompt tiếng Anh) với giám khảo Gemini qua LangChain."""

    def __init__(self, judge: BaseChatModel) -> None:
        _shim_vertexai()
        import ragas
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness
        from ragas.run_config import RunConfig

        self.version = ragas.__version__
        self.metric = Faithfulness(llm=LangchainLLMWrapper(judge))
        self.metric.init(RunConfig(timeout=180, max_retries=6, max_wait=90))

    def score(self, question: str, answer: str, contexts: Sequence[str]) -> float | None:
        from ragas.dataset_schema import SingleTurnSample

        sample = SingleTurnSample(
            user_input=question, response=answer, retrieved_contexts=list(contexts)
        )
        try:
            value = asyncio.run(self.metric.single_turn_ascore(sample))
        except Exception as e:  # lỗi parse/quota của một cảnh không làm hỏng cả lần chạy
            print(f"    ragas lỗi: {type(e).__name__}: {str(e)[:200]}")
            return None
        return None if value != value else float(value)  # NaN: không tách được khẳng định


# --- Cache --------------------------------------------------------------------------


def _key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]


class Cache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = (
            json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        )

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def put(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")


# --- Eval một sách ------------------------------------------------------------------


def _question(book: GoldenBook, scene: Scene) -> str:
    return f"Viết lời đọc phần `{scene.section}` cho video review sách {book.title}."


class BookEval:
    def __init__(
        self,
        book: GoldenBook,
        settings: Settings,
        writer: BaseChatModel,
        checker: FaithfulnessChecker,
        ragas: RagasScorer | None,
        embeddings: Any,
    ) -> None:
        self.book, self.settings, self.writer = book, settings, writer
        self.checker, self.ragas, self.embeddings = checker, ragas, embeddings
        self.dir = OUT / book.slug
        self.chunks = book.chunks()
        self.by_id = {c.id: c for c in self.chunks}
        self.cache = Cache(self.dir / "scores.json")

    def storyboard(self) -> Storyboard | None:
        path = self.dir / "storyboard.json"
        if path.is_file():
            return Storyboard.model_validate_json(path.read_text(encoding="utf-8"))
        runner = make_storyboard_runner(
            self.writer,
            InMemoryRetriever(self.chunks, self.embeddings),
            self.settings,
            spoiler_free=True,
        )
        b = self.book
        out = runner(
            {"book": {"title": b.title, "author": b.author, "year": b.year}, "kind": b.kind}
        )
        if "storyboard" not in out:
            print(f"  storyboard thất bại: {out.get('error_code')}")
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out["storyboard"], ensure_ascii=False, indent=1), "utf-8")
        (self.dir / "storyboard_cost.json").write_text(json.dumps(out["cost"]), "utf-8")
        return Storyboard.model_validate(out["storyboard"])

    def contexts(self, scene: Scene) -> list[str]:
        if scene.section in CITED_SECTIONS:
            return scene_contexts(scene, self.by_id)
        return [c.content for c in self.chunks]

    def judge(self, narration: str, contexts: list[str]) -> Judgement:
        key = _key("vi", JUDGE_PROMPT_VERSION, self.settings.judge_model, narration, *contexts)
        if (hit := self.cache.get(key)) is not None:
            return Judgement.model_validate(hit)
        j = self.checker.judge(narration, contexts)
        self.cache.put(key, j.model_dump())
        return j

    def ragas_score(self, scene: Scene, narration: str, contexts: list[str]) -> float | None:
        if self.ragas is None:
            return None
        key = _key("ragas", self.ragas.version, self.settings.judge_model, narration, *contexts)
        if key in self.cache.data:
            value = self.cache.get(key)
            return None if value is None else float(value)
        value = self.ragas.score(_question(self.book, scene), narration, contexts)
        if value is not None:  # lỗi thì lần sau chạy lại
            self.cache.put(key, value)
        return value

    def rewrite_loop(self, scene: Scene, contexts: list[str], first: Judgement) -> dict[str, Any]:
        key = _key("loop", REWRITE_PROMPT_VERSION, self.settings.gemini_model, scene.narration_vi)
        if (hit := self.cache.get(key)) is not None:
            return dict(hit)
        final, history = self.checker.check_scene(scene, contexts, initial=first)
        out = {
            "narration_vi": final.narration_vi,
            "on_screen_text_vi": final.on_screen_text_vi,
            "flags": final.flags,
            "rounds": [h.model_dump() for h in history],
        }
        self.cache.put(key, out)
        return out

    def run(self) -> dict[str, Any] | None:
        sb = self.storyboard()
        if sb is None:
            return None
        scenes: list[dict[str, Any]] = []
        for scene in sb.scenes:
            contexts = self.contexts(scene)
            first = self.judge(scene.narration_vi, contexts)
            row: dict[str, Any] = {
                "id": scene.id,
                "section": scene.section,
                "narration_vi": scene.narration_vi,
                "chunk_ids": [c.chunk_id for c in scene.citations],
                "vi": first.score,
                "vi_claims": [c.model_dump() for c in first.claims],
                "ragas": self.ragas_score(scene, scene.narration_vi, contexts),
            }
            if scene.section in CITED_SECTIONS:
                loop = self.rewrite_loop(scene, contexts, first)
                final = Judgement.model_validate(loop["rounds"][-1])
                row["rounds"] = len(loop["rounds"]) - 1
                row["vi_final"] = final.score
                row["flags"] = loop["flags"]
                if row["rounds"]:
                    row["final_narration_vi"] = loop["narration_vi"]
                    row["final_vi_claims"] = [c.model_dump() for c in final.claims]
                    row["ragas_final"] = self.ragas_score(scene, loop["narration_vi"], contexts)
                else:
                    row["ragas_final"] = row["ragas"]
            scenes.append(row)
            print(
                f"  cảnh {scene.id:>2} {scene.section:<10} vi={row['vi']:.2f}"
                f" ragas={_fmt(row['ragas'])}"
                + (f" → vi={row['vi_final']:.2f}" if row.get("rounds") else "")
            )
        cost_path = self.dir / "storyboard_cost.json"
        return {
            "slug": self.book.slug,
            "title": self.book.title,
            "kind": self.book.kind,
            "storyboard_cost": json.loads(cost_path.read_text()) if cost_path.is_file() else None,
            "sections": _section_summary(scenes),
            "scenes": scenes,
        }


# --- Tổng hợp -----------------------------------------------------------------------


def _fmt(v: float | None) -> str:
    return "  —" if v is None else f"{v:.2f}"


def _avg(values: Sequence[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 4) if vals else None


def _section_summary(scenes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for section in SECTION_ORDER:
        rows = [s for s in scenes if s["section"] == section]
        out[section] = {
            "n": len(rows),
            "vi": _avg([s["vi"] for s in rows]),
            "ragas": _avg([s["ragas"] for s in rows]),
        }
    cited = [s for s in scenes if s["section"] in CITED_SECTIONS]
    out["context_body"] = {
        "n": len(cited),
        "vi": _avg([s["vi"] for s in cited]),
        "ragas": _avg([s["ragas"] for s in cited]),
        "vi_final": _avg([s.get("vi_final") for s in cited]),
        "ragas_final": _avg([s.get("ragas_final") for s in cited]),
        "rewritten": sum(1 for s in cited if s.get("rounds")),
        "low_faithfulness": sum(1 for s in cited if "LOW_FAITHFULNESS" in s.get("flags", [])),
    }
    return out


def _manual(books: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not GRADES.is_file():
        return None
    by_key = {(b["slug"], s["id"]): s for b in books for s in b["scenes"]}
    rows = []
    for g in json.loads(GRADES.read_text(encoding="utf-8")):
        s = by_key.get((g["slug"], g["scene_id"]))
        if s is None or s["narration_vi"] != g["narration_vi"]:
            continue  # storyboard đã đổi, điểm tay không còn khớp
        rows.append({**g, "vi": s["vi"], "ragas": s["ragas"]})

    def mae(field: str) -> float | None:
        pairs = [(r["manual"], r[field]) for r in rows if r[field] is not None]
        return round(mean(abs(a - b) for a, b in pairs), 4) if pairs else None

    def agree(field: str) -> float | None:
        t = 0.9  # cùng phía ngưỡng thì pipeline xử lý giống chấm tay
        pairs = [(r["manual"], r[field]) for r in rows if r[field] is not None]
        return round(mean((a >= t) == (b >= t) for a, b in pairs), 4) if pairs else None

    return {
        "n": len(rows),
        "manual_mean": _avg([r["manual"] for r in rows]),
        "vi_mean": _avg([r["vi"] for r in rows]),
        "ragas_mean": _avg([r["ragas"] for r in rows]),
        "mae_vi": mae("vi"),
        "mae_ragas": mae("ragas"),
        "threshold_agreement_vi": agree("vi"),
        "threshold_agreement_ragas": agree("ragas"),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slugs", nargs="*")
    parser.add_argument("--no-ragas", action="store_true", help="bỏ RAGAS gốc, đỡ quota")
    parser.add_argument("--rpm", type=float, default=8.0, help="request/phút mỗi model")
    args = parser.parse_args()

    settings = get_settings().model_copy(update={"llm_rpm": args.rpm})
    if settings.judge_model == settings.gemini_model:
        raise SystemExit("JUDGE_MODEL phải khác GEMINI_MODEL (không tự chấm cho mình)")
    writer, judge = make_chat_model(settings), make_judge_model(settings)
    checker = FaithfulnessChecker(judge, writer, settings)
    ragas = None if args.no_ragas else RagasScorer(judge)
    embeddings = make_embeddings(settings)

    started = time.time()
    books = []
    for book in load_golden(GOLDEN):
        if args.slugs and book.slug not in args.slugs:
            continue
        print(f"\n=== {book.title}")
        result = BookEval(book, settings, writer, checker, ragas, embeddings).run()
        if result is not None:
            books.append(result)

    all_scenes = [s for b in books for s in b["scenes"]]
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "writer_model": settings.gemini_model,
        "judge_model": settings.judge_model,
        "threshold": settings.faithfulness_threshold,
        "rewrite_rounds": settings.faithfulness_rounds,
        "prompts": [JUDGE_PROMPT_VERSION, REWRITE_PROMPT_VERSION],
        "ragas_version": ragas.version if ragas else None,
        "scope": (
            "Ngưỡng tính trên context/body (nguồn = chunk cảnh trích dẫn). hook và review_cta "
            "đo riêng, đối chiếu với toàn bộ nguồn của sách, không tính vào ngưỡng."
        ),
        "books_failed": [
            b.slug
            for b in load_golden(GOLDEN)
            if (not args.slugs or b.slug in args.slugs) and b.slug not in {x["slug"] for x in books}
        ],
        "summary": _section_summary(all_scenes),
        "manual": _manual(books),
        "judge_cost": checker.cost(),
        "books": books,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nĐã ghi {REPORT.relative_to(ROOT)} sau {time.time() - started:.0f}s")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=1))
    if report["manual"]:
        m = {k: v for k, v in report["manual"].items() if k != "rows"}
        print("chấm tay:", json.dumps(m, ensure_ascii=False))


if __name__ == "__main__":
    main()
