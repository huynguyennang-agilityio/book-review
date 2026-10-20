"""Mã lỗi ổn định trả về cho frontend dưới dạng {code, message_vi, retryable}."""

from enum import StrEnum

from pydantic import BaseModel


class ErrorCode(StrEnum):
    BOOK_NOT_FOUND = "BOOK_NOT_FOUND"
    GENRE_EXCLUDED = "GENRE_EXCLUDED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    LOW_FAITHFULNESS = "LOW_FAITHFULNESS"
    RENDER_FAILED = "RENDER_FAILED"
    CANCELLED = "CANCELLED"


class ErrorResponse(BaseModel):
    code: ErrorCode
    message_vi: str
    retryable: bool
