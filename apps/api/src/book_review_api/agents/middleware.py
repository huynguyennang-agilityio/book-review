"""Middleware cho research agent: giới hạn số vòng, che PII, tóm tắt, chi phí, thể loại.

`CostTrackingMiddleware` và `GenreGuardMiddleware` tự viết (mục 3.1 plan v5). Cả hai dừng agent
bằng `jump_to="end"` và ghi `error_code` vào state để node `research_agent` đổi thành status
của graph.
"""

import json
from typing import Any, NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
    hook_config,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.runtime import Runtime

from book_review_api.config import Settings
from book_review_api.errors import ERROR_SPECS, ErrorCode
from book_review_api.rag.pii import PHONE_RE


class ResearchState(AgentState[Any]):
    """State của agent: thêm bộ đếm chi phí và mã lỗi do middleware đặt."""

    cost_usd: NotRequired[float]
    input_tokens: NotRequired[int]
    output_tokens: NotRequired[int]
    error_code: NotRequired[str]


def _stop(code: ErrorCode) -> dict[str, Any]:
    return {
        "jump_to": "end",
        "error_code": code.value,
        "messages": [AIMessage(content=ERROR_SPECS[code].message_vi)],
    }


class CostTrackingMiddleware(AgentMiddleware[ResearchState, None, Any]):
    """Cộng token và chi phí của mỗi lần gọi model vào state; vượt ngân sách thì dừng."""

    state_schema = ResearchState

    def __init__(
        self, budget_usd: float, price_input_per_mtok: float, price_output_per_mtok: float
    ) -> None:
        super().__init__()
        self.budget_usd = budget_usd
        self.price_in = price_input_per_mtok
        self.price_out = price_output_per_mtok

    def after_model(self, state: ResearchState, runtime: Runtime[None]) -> dict[str, Any] | None:
        last = state["messages"][-1] if state["messages"] else None
        usage = getattr(last, "usage_metadata", None) if isinstance(last, AIMessage) else None
        if not usage:
            return None
        n_in = int(usage.get("input_tokens", 0))
        n_out = int(usage.get("output_tokens", 0))
        usd = (n_in * self.price_in + n_out * self.price_out) / 1_000_000
        return {
            "cost_usd": state.get("cost_usd", 0.0) + usd,
            "input_tokens": state.get("input_tokens", 0) + n_in,
            "output_tokens": state.get("output_tokens", 0) + n_out,
        }

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: ResearchState, runtime: Runtime[None]) -> dict[str, Any] | None:
        if state.get("cost_usd", 0.0) >= self.budget_usd:
            return _stop(ErrorCode.BUDGET_EXCEEDED)
        return None


def _genre_excluded(message: ToolMessage) -> bool:
    if message.name != "check_genre":
        return False
    try:
        data = json.loads(message.content) if isinstance(message.content, str) else {}
    except ValueError:
        return False
    return isinstance(data, dict) and bool(data.get("excluded"))


class GenreGuardMiddleware(AgentMiddleware[ResearchState, None, Any]):
    """Dừng ngay khi `check_genre` báo thể loại bị loại trừ, trước khi tốn thêm vòng nào."""

    state_schema = ResearchState

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: ResearchState, runtime: Runtime[None]) -> dict[str, Any] | None:
        for message in reversed(state["messages"]):
            if isinstance(message, ToolMessage) and _genre_excluded(message):
                return _stop(ErrorCode.GENRE_EXCLUDED)
        return None


def research_middleware(
    settings: Settings, model: BaseChatModel
) -> list[AgentMiddleware[Any, Any, Any]]:
    """Thứ tự: che PII trước khi gửi LLM, tóm tắt, rồi các lớp chặn."""
    return [
        PIIMiddleware("email", apply_to_tool_results=True),
        PIIMiddleware("credit_card", apply_to_tool_results=True),
        PIIMiddleware("phone_vn", detector=PHONE_RE.pattern, apply_to_tool_results=True),
        SummarizationMiddleware(model=model, trigger=("tokens", 12_000), keep=("messages", 8)),
        GenreGuardMiddleware(),
        CostTrackingMiddleware(
            settings.research_budget_usd,
            settings.price_input_per_mtok,
            settings.price_output_per_mtok,
        ),
        # Gói free của Gemini chỉ 5 RPM: gặp 429 thì chờ cửa sổ phút trôi qua rồi thử lại.
        ModelRetryMiddleware(max_retries=3, initial_delay=15.0, max_delay=60.0, on_failure="error"),
        ModelCallLimitMiddleware(run_limit=settings.research_model_call_limit),
        ToolCallLimitMiddleware(run_limit=settings.research_tool_call_limit),
    ]
