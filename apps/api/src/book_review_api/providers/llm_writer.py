"""Model viết kịch bản: OpenAI (mặc định khi có key) hoặc Gemini như cũ."""

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from book_review_api.config import Settings, get_settings
from book_review_api.providers.llm_gemini import make_chat_model


def writer_uses_openai(settings: Settings) -> bool:
    provider = settings.writer_provider
    if provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("Thiếu OPENAI_API_KEY cho WRITER_PROVIDER=openai")
        return True
    return provider == "auto" and bool(settings.openai_api_key)


def make_writer_model(settings: Settings | None = None) -> BaseChatModel:
    """Chat model viết storyboard và viết lại cảnh. Không có OpenAI thì dùng `gemini_model`."""
    settings = settings or get_settings()
    if not writer_uses_openai(settings):
        return make_chat_model(settings)
    from langchain_core.rate_limiters import InMemoryRateLimiter
    from langchain_openai import ChatOpenAI

    limiter = (
        InMemoryRateLimiter(requests_per_second=settings.llm_rpm / 60, max_bucket_size=1)
        if settings.llm_rpm > 0
        else None
    )
    return ChatOpenAI(
        model=settings.writer_model,
        api_key=SecretStr(settings.openai_api_key),
        timeout=120,
        max_retries=0,  # thử lại do `call_structured` lo, để không chờ hai lớp
        rate_limiter=limiter,
    )
