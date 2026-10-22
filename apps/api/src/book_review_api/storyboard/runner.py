"""Chạy storyboard cho kết quả research, trả phần cập nhật cho state của graph."""

import logging
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel

from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.storyboard.schema import BookIdentity
from book_review_api.storyboard.writer import Retrieve, StoryboardError, StoryboardWriter

log = logging.getLogger(__name__)

# Nhận `research` trong state, trả `{"storyboard": ..., "cost": ...}` hoặc status lỗi.
StoryboardRunner = Callable[[dict[str, Any]], dict[str, Any]]


def make_storyboard_runner(
    model: BaseChatModel,
    retrieve: Retrieve,
    settings: Settings | None = None,
    *,
    spoiler_free: bool = True,
) -> StoryboardRunner:
    settings = settings or get_settings()

    def run(research: dict[str, Any]) -> dict[str, Any]:
        book = BookIdentity.model_validate(research["book"])
        writer = StoryboardWriter(model, retrieve, settings, spoiler_free=spoiler_free)
        try:
            storyboard = writer.write(book, research["kind"])
        except StoryboardError as e:
            log.warning("storyboard thất bại: %s; %s", e, e.problems)
            return {
                "cost": _cost(writer, settings),
                "status": "failed",
                "error_code": ErrorCode.LOW_FAITHFULNESS.value,
            }
        return {"storyboard": storyboard.model_dump(), "cost": _cost(writer, settings)}

    return run


def _cost(writer: StoryboardWriter, settings: Settings) -> dict[str, float]:
    n_in, n_out = writer.usage.input_tokens, writer.usage.output_tokens
    usd = writer.usage.usd_for(settings)
    return {"usd": usd, "input_tokens": float(n_in), "output_tokens": float(n_out)}
