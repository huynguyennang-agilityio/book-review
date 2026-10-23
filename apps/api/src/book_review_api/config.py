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
    # Giá riêng theo model (USD/1 triệu token: input, output); model không có ở đây dùng giá trên.
    model_prices: dict[str, tuple[float, float]] = {
        "gpt-5.4-mini": (0.75, 4.50),
        "gpt-5-mini": (0.25, 2.00),
    }

    # Model viết kịch bản (storyboard, viết lại cảnh): "openai", "gemini" hoặc "auto" (OpenAI khi
    # có OPENAI_API_KEY, không thì Gemini như cũ).
    writer_provider: str = "auto"
    writer_model: str = "gpt-5.4-mini"
    # Dự phòng khi model chính quá tải (503, 429, timeout). Rỗng = không dự phòng.
    # Model viết (OpenAI) rơi về Gemini `writer_fallback_model`; giám khảo và các bước Gemini
    # khác (rerank, prompt ảnh) rơi về `judge_fallback_model` / `gemini_fallback_model`.
    writer_fallback_model: str = "gemini-3.5-flash-lite"
    judge_fallback_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str = "gemini-3.1-flash-lite"
    openai_api_key: str = ""

    # Storyboard (ngày 10): độ dài video đích và số lần viết lại một phần khi citation sai.
    storyboard_minutes: int = 3
    storyboard_retries: int = 2
    # Viết lại hết lượt vẫn còn cảnh trích sai: sửa riêng từng cảnh tối đa chừng này lần trước
    # khi bỏ cảnh. 0 = bỏ luôn.
    storyboard_scene_repairs: int = 2

    # Faithfulness (ngày 11): giám khảo dùng model khác model viết kịch bản. Cảnh context/body
    # dưới ngưỡng được viết lại tối đa `faithfulness_rounds` vòng rồi gắn cờ LOW_FAITHFULNESS.
    judge_model: str = "gemini-3.1-flash-lite"
    faithfulness_threshold: float = 0.9
    faithfulness_rounds: int = 2
    # Giới hạn request/phút cho chat model (0 = không giới hạn). Gói free Gemini ~5-10 RPM.
    llm_rpm: float = 0.0

    # Ước tính chi phí media (ngày 11). Seedream v4 edit 0,03 USD/ảnh (ADR 0003); edge-tts miễn
    # phí; I2V (Phase 2) tính theo clip, `i2v_clips` = 0 khi chưa bật.
    price_image_usd: float = 0.03
    # Trần ngân sách người dùng được đặt khi chạy lại project lỗi, chặn gõ nhầm.
    max_budget_usd: float = 20.0
    images_per_scene: int = 1
    character_sheet_images: int = 4
    # Số nhân vật chính tối đa được tạo sheet (ngày 16) và kích thước sheet (ngang, nhiều góc).
    character_max: int = 3
    character_sheet_width: int = 1920
    character_sheet_height: int = 1080
    # Ảnh cảnh (ngày 18): 25-35 ảnh mỗi video, tạo ở ~9:16 (bội số 16) rồi crop ra 720x1280.
    scene_images_min: int = 25
    scene_images_max: int = 35
    scene_image_width: int = 1088
    scene_image_height: int = 1920
    scene_out_width: int = 720
    scene_out_height: int = 1280
    scene_max_characters: int = 2
    fal_key: str = ""
    fal_concurrency: int = 4
    price_tts_per_mchar: float = 0.0
    price_i2v_per_clip: float = 0.35
    i2v_clips: int = 0

    # Hàng đợi render (ngày 12): arq + Redis. Worker làm TTS/timeline/ảnh/video.
    redis_url: str = "redis://localhost:6379"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    # Thư mục media dùng chung với worker; đường dẫn asset trong state tương đối so với nó.
    media_dir: str = "var/media"
    # Thời gian tối đa graph chờ một job của worker.
    job_timeout_s: float = 600.0
    # Khoảng nghỉ giữa hai cảnh (0,15–0,3 s).
    scene_gap_s: float = 0.2

    def price_for(self, model: str) -> tuple[float, float]:
        """Giá (input, output) của model; tên có hậu tố phiên bản (gpt-5.4-mini-2026-...) khớp
        theo tiền tố dài nhất."""
        name = model.removeprefix("models/")
        match = max((k for k in self.model_prices if name.startswith(k)), key=len, default=None)
        if match is None:
            return self.price_input_per_mtok, self.price_output_per_mtok
        return self.model_prices[match]

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
