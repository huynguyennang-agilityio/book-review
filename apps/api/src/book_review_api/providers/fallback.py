"""Dự phòng khi model quá tải: lỗi 503/5xx, 429, timeout hoặc mất kết nối thì chuyển ngay sang
model dự phòng. Lỗi khác (key sai, request sai) vẫn ném ra như cũ.

Dùng các lỗi chuẩn của langchain-core nên áp được cho cả Gemini lẫn OpenAI. Kết quả vẫn dùng
được như chat model (`with_structured_output`, `invoke`) vì `RunnableWithFallbacks` chuyển các
lời gọi đó sang cả model chính lẫn model dự phòng. Không dùng cho agent cần `BaseChatModel` thật.
"""

from typing import cast

from langchain_core.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langchain_core.language_models import BaseChatModel

OVERLOAD_ERRORS: tuple[type[BaseException], ...] = (
    ModelAPIError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelConnectionError,
)


def with_overload_fallback(primary: BaseChatModel, fallback: BaseChatModel | None) -> BaseChatModel:
    if fallback is None:
        return primary
    return cast(
        BaseChatModel, primary.with_fallbacks([fallback], exceptions_to_handle=OVERLOAD_ERRORS)
    )
