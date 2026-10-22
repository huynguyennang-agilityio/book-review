"""Gemini: embeddings cho RAG và chat model (rerank, agent)."""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from pydantic import SecretStr

from book_review_api.config import Settings, get_settings
from book_review_api.providers.fallback import with_overload_fallback


def make_embeddings(settings: Settings | None = None) -> Embeddings:
    """Embedding đa ngôn ngữ (model và số chiều đặt trong config).

    Tài liệu dùng task type RETRIEVAL_DOCUMENT, câu hỏi dùng RETRIEVAL_QUERY (mặc định của lớp).
    """
    settings = settings or get_settings()
    if not settings.google_api_key:
        raise RuntimeError("Thiếu GOOGLE_API_KEY để tạo embeddings")
    return GoogleGenerativeAIEmbeddings(
        model=f"models/{settings.embedding_model}",
        api_key=SecretStr(settings.google_api_key),
        output_dimensionality=settings.embedding_dim,
    )


def make_chat_model(
    settings: Settings | None = None, model: str | None = None, max_retries: int = 6
) -> BaseChatModel:
    """Chat model Gemini (mặc định `gemini_model` trong config), nhiệt độ 0 cho việc chấm/rerank.

    `llm_rpm` > 0 thì giới hạn số request mỗi phút (gói free). Model có dự phòng nên đặt
    `max_retries` thấp để chuyển sang dự phòng sớm thay vì tự thử lại lâu.
    """
    settings = settings or get_settings()
    if not settings.google_api_key:
        raise RuntimeError("Thiếu GOOGLE_API_KEY để tạo chat model")
    limiter = (
        InMemoryRateLimiter(requests_per_second=settings.llm_rpm / 60, max_bucket_size=1)
        if settings.llm_rpm > 0
        else None
    )
    return ChatGoogleGenerativeAI(
        model=model or settings.gemini_model,
        api_key=SecretStr(settings.google_api_key),
        temperature=0,
        rate_limiter=limiter,
        max_retries=max_retries,
    )


def make_gemini_with_fallback(
    settings: Settings | None = None, model: str | None = None, fallback: str | None = None
) -> BaseChatModel:
    """Gemini `model` (mặc định `gemini_model`), quá tải thì chuyển sang `fallback` (mặc định
    `gemini_fallback_model`). Không dùng cho research agent (cần `BaseChatModel` thật)."""
    settings = settings or get_settings()
    name = model or settings.gemini_model
    backup = settings.gemini_fallback_model if fallback is None else fallback
    if not backup or backup == name:
        return make_chat_model(settings, name)
    return with_overload_fallback(
        make_chat_model(settings, name, max_retries=1), make_chat_model(settings, backup)
    )


def make_judge_model(settings: Settings | None = None) -> BaseChatModel:
    """Giám khảo faithfulness: model khác model viết kịch bản để không tự chấm cho mình."""
    settings = settings or get_settings()
    return make_gemini_with_fallback(settings, settings.judge_model, settings.judge_fallback_model)
