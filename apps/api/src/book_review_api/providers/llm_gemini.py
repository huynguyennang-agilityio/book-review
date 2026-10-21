"""Gemini: embeddings cho RAG và chat model (rerank, agent)."""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from pydantic import SecretStr

from book_review_api.config import Settings, get_settings


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


def make_chat_model(settings: Settings | None = None, model: str | None = None) -> BaseChatModel:
    """Chat model Gemini (mặc định `gemini_model` trong config), nhiệt độ 0 cho việc chấm/rerank.

    `llm_rpm` > 0 thì giới hạn số request mỗi phút (gói free).
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
    )


def make_judge_model(settings: Settings | None = None) -> BaseChatModel:
    """Giám khảo faithfulness: model khác model viết kịch bản để không tự chấm cho mình."""
    settings = settings or get_settings()
    return make_chat_model(settings, settings.judge_model)
