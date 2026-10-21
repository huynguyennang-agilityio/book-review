"""Cấu hình đọc từ biến môi trường và file `.env` (xem `.env.example`)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "local"

    # Postgres: bảng ứng dụng (RLS), checkpoint và store của LangGraph. Trên Supabase dùng
    # chuỗi kết nối trực tiếp hoặc session pooler (cổng 5432), không dùng transaction pooler.
    database_url: str = "postgresql://postgres:postgres@localhost:5432/book_review"

    # Supabase Auth. Project mới ký JWT bằng khoá bất đối xứng (ES256/RS256), public key lấy
    # từ JWKS `{supabase_url}/auth/v1/.well-known/jwks.json`. Project cũ dùng HS256 với
    # `supabase_jwt_secret`. Hỗ trợ cả hai, chọn theo `alg` trong header của token.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    # Embeddings (Gemini). `embedding_dim` phải khớp cột `vector(N)` trong migration 0004.
    google_api_key: str = ""
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # LLM chat (rerank ở ngày 7, agent ở các ngày sau).
    gemini_model: str = "gemini-3.5-flash"

    # Retrieval: gộp vector + full-text lấy `retrieve_top_k`, rerank xuống `rerank_top_n`.
    # `rerank_provider`: "none" (giữ thứ tự RRF) hoặc "llm" (Gemini chấm lại). Cross-encoder cắm
    # thêm bằng cách hiện thực `Reranker` trong `rag/retrieve.py`.
    retrieve_top_k: int = 8
    rerank_top_n: int = 4
    rerank_provider: str = "none"

    # Tìm web cho research agent: "gemini" (Google Search grounding, cần quota riêng) hoặc "tavily".
    search_provider: str = "gemini"
    tavily_api_key: str = ""

    # Research agent (ngày 9). Giá USD trên 1 triệu token, chỉnh theo bảng giá model đang dùng.
    research_min_sources: int = 4
    # Số lần nhắc agent tìm thêm khi dừng mà chưa đủ nguồn.
    research_nudges: int = 2
    research_budget_usd: float = 0.3
    research_model_call_limit: int = 40
    research_tool_call_limit: int = 60
    price_input_per_mtok: float = 0.30
    price_output_per_mtok: float = 2.50

    # Storyboard (ngày 10): độ dài video đích và số lần viết lại một phần khi citation sai.
    storyboard_minutes: int = 3
    storyboard_retries: int = 2

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
