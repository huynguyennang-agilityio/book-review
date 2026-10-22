"""Gọi chat model với structured output, thử lại khi lỗi mạng/quota và cộng dồn token."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

if TYPE_CHECKING:
    from book_review_api.config import Settings

log = logging.getLogger(__name__)

# Gói free của Gemini chỉ 5 RPM: chờ cửa sổ phút trôi qua rồi thử lại.
RETRY_DELAYS_S: tuple[float, ...] = (15.0, 30.0, 60.0)


class StructuredOutputError(Exception):
    """Model trả về nhưng không parse được theo schema."""


class Usage:
    """Token cộng dồn, tách theo model đã trả lời để tính tiền đúng giá từng model."""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.by_model: dict[str, list[int]] = {}

    def add(self, message: BaseMessage | None) -> None:
        meta = message.usage_metadata if isinstance(message, AIMessage) else None
        if meta:
            n_in, n_out = int(meta.get("input_tokens", 0)), int(meta.get("output_tokens", 0))
            self.input_tokens += n_in
            self.output_tokens += n_out
            name = str((message.response_metadata or {}).get("model_name") or "")  # type: ignore[union-attr]
            row = self.by_model.setdefault(name, [0, 0])
            row[0] += n_in
            row[1] += n_out

    def usd(self, price_input_per_mtok: float, price_output_per_mtok: float) -> float:
        return (
            self.input_tokens * price_input_per_mtok + self.output_tokens * price_output_per_mtok
        ) / 1e6

    def usd_for(self, settings: "Settings") -> float:
        """Tiền theo bảng giá từng model (`Settings.price_for`); model lạ dùng giá mặc định."""
        total = 0.0
        for name, (n_in, n_out) in self.by_model.items():
            p_in, p_out = settings.price_for(name)
            total += (n_in * p_in + n_out * p_out) / 1e6
        return total


def call_structured[T: BaseModel](
    model: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    usage: Usage,
    sleep: Callable[[float], None],
) -> T:
    structured = model.with_structured_output(schema, include_raw=True)
    for attempt in range(len(RETRY_DELAYS_S) + 1):
        try:
            out = cast(dict[str, Any], structured.invoke(messages))
        except Exception:
            if attempt == len(RETRY_DELAYS_S):
                raise
            log.warning("gọi model thất bại, thử lại sau %ss", RETRY_DELAYS_S[attempt])
            sleep(RETRY_DELAYS_S[attempt])
            continue
        usage.add(out.get("raw"))
        parsed = out.get("parsed")
        if isinstance(parsed, schema):
            return parsed
        if isinstance(parsed, dict):
            return schema.model_validate(parsed)
        raise StructuredOutputError(
            f"Model không trả về {schema.__name__} hợp lệ: {out.get('parsing_error')}"
        )
    raise AssertionError("unreachable")
