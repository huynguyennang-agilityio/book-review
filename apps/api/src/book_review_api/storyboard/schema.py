"""Schema của storyboard (mục 10 plan v5). Ảnh và shot được điền ở các ngày sau."""

from typing import Literal

from pydantic import BaseModel, Field

Section = Literal["hook", "context", "body", "review_cta"]
SceneType = Literal["character", "landscape", "metaphor", "action", "title"]

# Các phần bắt buộc có trích dẫn; hook và review_cta là lời dẫn, không đưa dữ kiện.
CITED_SECTIONS: frozenset[str] = frozenset({"context", "body"})
SECTION_ORDER: tuple[Section, ...] = ("hook", "context", "body", "review_cta")
MAX_QUOTE_CHARS = 200
# Số cảnh tối đa mỗi phần (khớp prompt storyboard_v1). Model đôi khi dồn cả kịch bản vào `hook`.
SECTION_MAX_SCENES: dict[str, int] = {"hook": 1, "context": 2, "body": 4, "review_cta": 2}


class Citation(BaseModel):
    source_id: str
    chunk_id: str
    quote: str = Field(description="Trích nguyên văn từ đoạn nguồn, tối đa 200 ký tự")


class BookIdentity(BaseModel):
    title: str
    author: str | None = None
    year: int | None = None
    original_title: str | None = None


class Character(BaseModel):
    name: str
    description_en: str = Field(description="Mô tả ngoại hình bằng tiếng Anh, dùng để tạo ảnh")


class SceneImage(BaseModel):
    prompt_en: str
    path: str | None = None


class Shot(BaseModel):
    image_ref: int = 0
    duration_s: float | None = None


class Scene(BaseModel):
    id: int
    section: Section
    narration_vi: str
    citations: list[Citation] = Field(default_factory=list)
    scene_type: SceneType
    images: list[SceneImage] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    on_screen_text_vi: str | None = None
    mood: str
    faithfulness: float | None = None
    # Cờ cho người duyệt, vd "LOW_FAITHFULNESS" khi viết lại 2 vòng vẫn dưới ngưỡng.
    flags: list[str] = Field(default_factory=list)


class Storyboard(BaseModel):
    book: BookIdentity
    book_category: Literal["fiction", "non_fiction"]
    spoiler_free: bool
    hook_vi: str
    characters: list[Character] = Field(default_factory=list)
    scenes: list[Scene]
    style_prompt_en: str
    caption_vi: str
    hashtags: list[str] = Field(default_factory=list)
    prompt_version: str = ""
