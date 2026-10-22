"""Faithfulness của lời đọc (mục 8 plan v5) và vòng viết lại cảnh điểm thấp.

Cách tính theo RAGAS: tách lời đọc thành khẳng định đơn, đếm tỉ lệ khẳng định có căn cứ trong
nguồn. Khác RAGAS ở hai chỗ để chạy tốt với tiếng Việt và gói free: prompt tách khẳng định viết
bằng tiếng Việt (bỏ câu hỏi tu từ, lời kêu gọi), và tách + đối chiếu gộp trong một lần gọi.
`evals/run_ragas.py` chạy cả RAGAS gốc để đối chiếu.

Nguồn của một cảnh là nội dung các chunk mà cảnh đó trích dẫn. Chỉ cảnh `context`/`body` được
chấm trong pipeline; `hook` và `review_cta` đo riêng trong eval.
"""

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.prompt_loader import load_prompt
from book_review_api.providers.structured import Usage, call_structured
from book_review_api.rag.retrieve import Chunk
from book_review_api.storyboard.schema import (
    CITED_SECTIONS,
    Scene,
    Storyboard,
    UnsupportedClaim,
)
from book_review_api.storyboard.writer import clean_narration

log = logging.getLogger(__name__)

JUDGE_PROMPT_VERSION = "faithfulness_judge_v1"
REWRITE_PROMPT_VERSION = "faithfulness_rewrite_v1"
LOW_FAITHFULNESS = ErrorCode.LOW_FAITHFULNESS.value

# Lấy chunk theo id (DB khi chạy thật, dict khi eval).
GetChunks = Callable[[Sequence[str]], Mapping[str, Chunk]]


class ClaimVerdict(BaseModel):
    claim: str = Field(description="Một khẳng định đơn, tự đứng được, tiếng Việt")
    supported: bool = Field(description="true nếu nguồn nói rõ hoặc suy ra trực tiếp được")
    reason: str = Field(description="Một câu ngắn: căn cứ trong nguồn hoặc nguồn thiếu gì")


class Judgement(BaseModel):
    claims: list[ClaimVerdict] = Field(default_factory=list)

    @property
    def score(self) -> float:
        """Tỉ lệ khẳng định có căn cứ; không có khẳng định nào thì không có gì sai (1.0)."""
        if not self.claims:
            return 1.0
        return sum(c.supported for c in self.claims) / len(self.claims)

    @property
    def unsupported(self) -> list[ClaimVerdict]:
        return [c for c in self.claims if not c.supported]


class SceneRewrite(BaseModel):
    narration_vi: str
    on_screen_text_vi: str | None = None


def _load(name: str) -> str:
    return load_prompt(name)


def _numbered(contexts: Sequence[str]) -> str:
    return "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, start=1)) or "(không có)"


class FaithfulnessChecker:
    def __init__(
        self,
        judge_model: BaseChatModel,
        writer_model: BaseChatModel,
        settings: Settings | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.judge_model = judge_model
        self.writer_model = writer_model
        self.settings = settings or get_settings()
        self.sleep = sleep
        self.judge_usage = Usage()
        self.writer_usage = Usage()
        self._judge_system = _load(JUDGE_PROMPT_VERSION)
        self._rewrite_system = _load(REWRITE_PROMPT_VERSION)

    def judge(self, narration: str, contexts: Sequence[str]) -> Judgement:
        human = f"Các đoạn nguồn:\n{_numbered(contexts)}\n\nLời đọc cần kiểm tra:\n{narration}"
        return call_structured(
            self.judge_model,
            Judgement,
            [SystemMessage(self._judge_system), HumanMessage(human)],
            self.judge_usage,
            self.sleep,
        )

    def rewrite(self, scene: Scene, contexts: Sequence[str], judgement: Judgement) -> Scene:
        bad = "\n".join(f"- {c.claim} ({c.reason})" for c in judgement.unsupported)
        human = (
            f"Các đoạn nguồn:\n{_numbered(contexts)}\n\n"
            f"Lời đọc cũ:\n{scene.narration_vi}\n"
            f"Chữ trên màn hình cũ: {scene.on_screen_text_vi or '(trống)'}\n\n"
            f"Các ý không có căn cứ trong nguồn:\n{bad or '- (không nêu cụ thể)'}\n\n"
            "Viết lại cảnh này, chỉ dùng thông tin trong nguồn."
        )
        out = call_structured(
            self.writer_model,
            SceneRewrite,
            [SystemMessage(self._rewrite_system), HumanMessage(human)],
            self.writer_usage,
            self.sleep,
        )
        return scene.model_copy(
            update={
                "narration_vi": clean_narration(out.narration_vi),
                "on_screen_text_vi": out.on_screen_text_vi,
            }
        )

    def check_scene(
        self, scene: Scene, contexts: Sequence[str], initial: Judgement | None = None
    ) -> tuple[Scene, list[Judgement]]:
        """Chấm, viết lại tối đa `faithfulness_rounds` vòng. Trả cảnh cuối và kết quả từng vòng.

        `initial` là kết quả chấm sẵn của cảnh (eval đã chấm thì không gọi lại giám khảo).
        """
        judgement = initial or self.judge(scene.narration_vi, contexts)
        history = [judgement]
        rounds = 0
        while judgement.score < self.settings.faithfulness_threshold:
            if rounds == self.settings.faithfulness_rounds:
                flags = list(dict.fromkeys([*scene.flags, LOW_FAITHFULNESS]))
                update = {
                    "faithfulness": judgement.score,
                    "flags": flags,
                    "unsupported": unsupported_claims(judgement),
                }
                return scene.model_copy(update=update), history
            scene = self.rewrite(scene, contexts, judgement)
            rounds += 1
            judgement = self.judge(scene.narration_vi, contexts)
            history.append(judgement)
        update = {"faithfulness": judgement.score, "unsupported": unsupported_claims(judgement)}
        return scene.model_copy(update=update), history

    def check(
        self, storyboard: Storyboard, chunks: Mapping[str, Chunk]
    ) -> tuple[Storyboard, dict[str, float]]:
        scenes: list[Scene] = []
        initial: list[float] = []
        final: list[float] = []
        rewritten = 0
        for scene in storyboard.scenes:
            if scene.section not in CITED_SECTIONS:
                scenes.append(scene)
                continue
            contexts = scene_contexts(scene, chunks)
            checked, history = self.check_scene(scene, contexts)
            initial.append(history[0].score)
            final.append(history[-1].score)
            rewritten += len(history) > 1
            scenes.append(checked)
        updated = storyboard.model_copy(update={"scenes": scenes})
        summary = {
            "faithfulness": _mean(final),
            "faithfulness_initial": _mean(initial),
            "faithfulness_min": min(final, default=1.0),
            "scenes_scored": float(len(final)),
            "scenes_rewritten": float(rewritten),
            "scenes_low_faithfulness": float(sum(LOW_FAITHFULNESS in s.flags for s in scenes)),
        }
        return updated, summary

    def cost(self) -> dict[str, float]:
        s = self.settings
        j, w = self.judge_usage, self.writer_usage
        return {
            "usd": j.usd(s.price_input_per_mtok, s.price_output_per_mtok)
            + w.usd(s.price_input_per_mtok, s.price_output_per_mtok),
            "input_tokens": float(j.input_tokens + w.input_tokens),
            "output_tokens": float(j.output_tokens + w.output_tokens),
        }


def unsupported_claims(judgement: Judgement) -> list[UnsupportedClaim]:
    return [UnsupportedClaim(claim=c.claim, reason=c.reason) for c in judgement.unsupported]


def scene_contexts(scene: Scene, chunks: Mapping[str, Chunk]) -> list[str]:
    """Nội dung các chunk cảnh trích dẫn, bỏ trùng, giữ thứ tự."""
    ids = list(dict.fromkeys(c.chunk_id for c in scene.citations))
    return [chunks[i].content for i in ids if i in chunks]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 1.0


# Nhận storyboard (dict) trong state, trả `{"storyboard", "eval_scores", "cost"}`.
FaithfulnessRunner = Callable[[dict[str, Any]], dict[str, Any]]


def make_faithfulness_runner(
    judge_model: BaseChatModel,
    writer_model: BaseChatModel,
    get_chunks: GetChunks,
    settings: Settings | None = None,
) -> FaithfulnessRunner:
    settings = settings or get_settings()

    def run(storyboard: dict[str, Any]) -> dict[str, Any]:
        sb = Storyboard.model_validate(storyboard)
        ids = [c.chunk_id for s in sb.scenes for c in s.citations]
        checker = FaithfulnessChecker(judge_model, writer_model, settings)
        updated, scores = checker.check(sb, get_chunks(ids))
        log.info(
            "faithfulness %.3f (ban đầu %.3f)",
            scores["faithfulness"],
            scores["faithfulness_initial"],
        )
        return {
            "storyboard": updated.model_dump(),
            "eval_scores": scores,
            "cost": checker.cost(),
        }

    return run
