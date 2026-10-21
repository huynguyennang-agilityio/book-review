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

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
