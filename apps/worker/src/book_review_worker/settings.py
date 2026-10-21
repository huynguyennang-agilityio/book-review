"""Cấu hình worker từ biến môi trường."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    redis_url: str = "redis://localhost:6379"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_concurrency: int = 2
    # Thư mục gốc cho audio/ảnh/video. API và worker phải thấy cùng thư mục (volume dùng chung).
    media_dir: str = "var/media"
