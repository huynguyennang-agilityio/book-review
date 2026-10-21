"""Viết lại một cảnh theo yêu cầu bằng lời của người duyệt kịch bản (ngày 15)."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from book_review_api.config import Settings, get_settings
from book_review_api.providers.structured import Usage, call_structured
from book_review_api.storyboard.faithfulness import (
    FaithfulnessChecker,
    GetChunks,
    SceneRewrite,
    _numbered,
    scene_contexts,
    unsupported_claims,
)
from book_review_api.storyboard.schema import CITED_SECTIONS, Storyboard
from book_review_api.storyboard.writer import clean_narration

PROMPT_VERSION = "scene_rewrite_instruction_v1"
_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.md"


class SceneNotFound(Exception):
    pass


# (storyboard, scene_id, yêu cầu, lời đọc hiện tại trong ô sửa) -> kết quả để UI hiển thị.
SceneRewriter = Callable[[dict[str, Any], int, str, str | None], dict[str, Any]]


def make_scene_rewriter(
    writer_model: BaseChatModel,
    judge_model: BaseChatModel,
    get_chunks: GetChunks,
    settings: Settings | None = None,
) -> SceneRewriter:
    settings = settings or get_settings()
    system = _PROMPT.read_text(encoding="utf-8")

    def run(
        storyboard: dict[str, Any], scene_id: int, instruction: str, narration: str | None
    ) -> dict[str, Any]:
        sb = Storyboard.model_validate(storyboard)
        scene = next((s for s in sb.scenes if s.id == scene_id), None)
        if scene is None:
            raise SceneNotFound(scene_id)
        chunks = get_chunks([c.chunk_id for c in scene.citations])
        contexts = scene_contexts(scene, chunks)
        current = (narration or "").strip() or scene.narration_vi
        human = (
            f"Phần của cảnh: {scene.section}\n"
            f"Các đoạn nguồn:\n{_numbered(contexts)}\n\n"
            f"Lời đọc hiện tại:\n{current}\n"
            f"Chữ trên màn hình hiện tại: {scene.on_screen_text_vi or '(trống)'}\n\n"
            f"Yêu cầu của người duyệt: {instruction.strip()}"
        )
        usage = Usage()
        out = call_structured(
            writer_model,
            SceneRewrite,
            [SystemMessage(system), HumanMessage(human)],
            usage,
            time.sleep,
        )
        text = clean_narration(out.narration_vi)
        checker = FaithfulnessChecker(judge_model, writer_model, settings)
        score: float | None = None
        unsupported: list[dict[str, str]] = []
        if scene.section in CITED_SECTIONS and contexts:
            judgement = checker.judge(text, contexts)
            score = judgement.score
            unsupported = [c.model_dump() for c in unsupported_claims(judgement)]
        usd = usage.usd(settings.price_input_per_mtok, settings.price_output_per_mtok)
        usd += checker.cost()["usd"]
        return {
            "scene_id": scene_id,
            "narration_vi": text,
            "on_screen_text_vi": out.on_screen_text_vi,
            "faithfulness": score,
            "unsupported": unsupported,
            "cost_usd": usd,
        }

    return run
