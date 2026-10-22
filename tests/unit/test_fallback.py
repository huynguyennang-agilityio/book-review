"""Dự phòng khi model quá tải: 503/429/timeout chuyển model, lỗi khác thì không."""

from typing import Any

import pytest
from langchain_core.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from book_review_api.config import Settings
from book_review_api.providers.fallback import with_overload_fallback
from book_review_api.providers.structured import Usage, call_structured


class Answer(BaseModel):
    text: str


class Model(GenericFakeChatModel):
    """Model giả: `errors` là các lỗi ném lần lượt trước khi trả lời đúng."""

    name_: str = "m"
    errors: list[Any] = []
    calls: int = 0

    # Kiểu trả về phải là Runnable để `RunnableWithFallbacks` áp lời gọi cho cả model dự phòng.
    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        def run(_messages: Any) -> dict[str, Any]:
            self.calls += 1
            if self.errors:
                raise self.errors.pop(0)
            raw = AIMessage(
                "",
                usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                response_metadata={"model_name": self.name_},
            )
            return {"raw": raw, "parsed": schema(text=self.name_), "parsing_error": None}

        return RunnableLambda(run)


def model(name: str, *errors: Exception) -> Model:
    return Model(messages=iter([]), name_=name, errors=list(errors))


def ask(m: Any, usage: Usage | None = None, sleeps: list[float] | None = None) -> Answer:
    waits = sleeps if sleeps is not None else []
    return call_structured(m, Answer, [HumanMessage("x")], usage or Usage(), waits.append)


@pytest.mark.parametrize(
    "error",
    [ModelAPIError("503 UNAVAILABLE"), ModelRateLimitError("429"), ModelTimeoutError("timeout")],
)
def test_overload_switches_to_fallback_without_waiting(error: Exception) -> None:
    primary, backup = model("gpt-5.4-mini", error), model("gemini-3.5-flash-lite")
    sleeps: list[float] = []
    usage = Usage()
    out = ask(with_overload_fallback(primary, backup), usage, sleeps)
    assert out.text == "gemini-3.5-flash-lite"
    assert sleeps == []
    assert list(usage.by_model) == ["gemini-3.5-flash-lite"]


def test_other_errors_do_not_switch_model() -> None:
    primary = model("gpt-5.4-mini", *[ModelAuthenticationError("401")] * 4)
    backup = model("gemini-3.5-flash-lite")
    with pytest.raises(ModelAuthenticationError):
        ask(with_overload_fallback(primary, backup))
    assert backup.calls == 0


def test_both_overloaded_waits_then_retries_primary() -> None:
    primary = model("gpt-5.4-mini", ModelAPIError("503"))
    backup = model("gemini-3.5-flash-lite", ModelAPIError("503"))
    sleeps: list[float] = []
    out = ask(with_overload_fallback(primary, backup), sleeps=sleeps)
    assert out.text == "gpt-5.4-mini"
    assert sleeps == [15.0]


def test_cost_uses_model_that_answered() -> None:
    s = Settings(price_input_per_mtok=0.3, price_output_per_mtok=2.5)
    usage = Usage()
    ask(with_overload_fallback(model("gpt-5.4-mini"), model("gemini-3.5-flash-lite")), usage)
    assert usage.usd_for(s) == pytest.approx((1000 * 0.75 + 100 * 4.5) / 1e6)


def test_no_fallback_returns_primary() -> None:
    primary = model("a")
    assert with_overload_fallback(primary, None) is primary
