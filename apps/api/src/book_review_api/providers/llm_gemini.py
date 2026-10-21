"""Gemini: embeddings cho RAG (LLM chat thêm ở các ngày sau)."""

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
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
