"""Gemini: embeddings cho RAG và chat model (rerank, agent)."""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
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


def make_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Chat model Gemini (tên model đặt trong config), nhiệt độ 0 cho việc chấm/rerank."""
    settings = settings or get_settings()
    if not settings.google_api_key:
        raise RuntimeError("Thiếu GOOGLE_API_KEY để tạo chat model")
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        api_key=SecretStr(settings.google_api_key),
        temperature=0,
    )
