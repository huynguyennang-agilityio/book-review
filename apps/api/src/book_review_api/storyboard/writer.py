"""Viết storyboard từ các đoạn truy xuất: dàn ý -> query từng phần -> retrieve -> viết từng phần.

Mọi lần gọi model dùng structured output. Citation do model chọn theo số thứ tự đoạn
(`[1]`, `[2]`...) rồi được đổi thành `chunk_id`/`source_id` thật, nên model không thể bịa id.
Phần nào vi phạm validator thì được gửi lại kèm danh sách lỗi, tối đa `storyboard_retries` lần.
"""

import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from book_review_api.config import Settings, get_settings
from book_review_api.rag.retrieve import Chunk
from book_review_api.storyboard.schema import (
    CITED_SECTIONS,
    MAX_QUOTE_CHARS,
    SECTION_ORDER,
    BookIdentity,
    Character,
    Citation,
    Scene,
    SceneType,
    Section,
    Storyboard,
)
from book_review_api.storyboard.validate import scene_problems

log = logging.getLogger(__name__)

PROMPT_VERSION = "storyboard_v1"
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.md"

# Gói free của Gemini chỉ 5 RPM: chờ cửa sổ phút trôi qua rồi thử lại.
RETRY_DELAYS_S: tuple[float, ...] = (15.0, 30.0, 60.0)
# Số đoạn tối đa đưa cho model viết một phần.
MAX_PASSAGES = 12

T = TypeVar("T", bound=BaseModel)
Retrieve = Callable[[str], list[Chunk]]


class StoryboardError(Exception):
    """Không viết được storyboard hợp lệ; `problems` là lỗi validator cuối cùng."""

    def __init__(self, message: str, problems: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.problems = list(problems)


# --- Cấu trúc đầu ra của model --------------------------------------------------


class OutlineSection(BaseModel):
    section: Literal["hook", "context", "body", "review_cta"]
    brief: str = Field(description="Phần này nói gì, 1-2 câu")
    queries: list[str] = Field(
        description="1-3 câu truy vấn tìm trong kho nguồn để viết phần này", min_length=1
    )


class Outline(BaseModel):
    characters: list[Character] = Field(
        default_factory=list, description="Nhân vật chính (chỉ sách hư cấu), tối đa 4"
    )
    style_prompt_en: str = Field(description="Phong cách hình ảnh chung, tiếng Anh")
    caption_vi: str = Field(description="Caption đăng TikTok, tiếng Việt, dưới 150 ký tự")
    hashtags: list[str] = Field(default_factory=list, description="3-6 hashtag, có dấu #")
    sections: list[OutlineSection]


class CitationDraft(BaseModel):
    passage: int = Field(description="Số thứ tự đoạn nguồn, ví dụ 2 cho [2]")
    quote: str = Field(description="Trích NGUYÊN VĂN từ đoạn đó, tối đa 200 ký tự")


class SceneDraft(BaseModel):
    narration_vi: str
    scene_type: SceneType
    mood: str
    on_screen_text_vi: str | None = None
    citations: list[CitationDraft] = Field(default_factory=list)


class SectionDraft(BaseModel):
    scenes: list[SceneDraft] = Field(min_length=1, max_length=6)


# --- Gọi model ------------------------------------------------------------------


class Usage:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0

    def add(self, message: BaseMessage | None) -> None:
        meta = message.usage_metadata if isinstance(message, AIMessage) else None
        if meta:
            self.input_tokens += int(meta.get("input_tokens", 0))
            self.output_tokens += int(meta.get("output_tokens", 0))


def trim_quote(quote: str) -> str:
    """Quote dài quá giới hạn thì cắt ở ranh giới từ: đoạn đầu của một trích nguyên văn vẫn
    là trích nguyên văn."""
    quote = quote.strip()
    if len(quote) <= MAX_QUOTE_CHARS:
        return quote
    cut = quote[:MAX_QUOTE_CHARS]
    head, sep, _ = cut.rpartition(" ")
    return (head if sep and head else cut).rstrip()


def load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class StoryboardWriter:
    def __init__(
        self,
        model: BaseChatModel,
        retrieve: Retrieve,
        settings: Settings | None = None,
        *,
        spoiler_free: bool = True,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.retrieve = retrieve
        self.settings = settings or get_settings()
        self.spoiler_free = spoiler_free
        self.sleep = sleep
        self.usage = Usage()
        self._system = load_prompt()

    def _call(self, schema: type[T], messages: list[BaseMessage]) -> T:
        structured = self.model.with_structured_output(schema, include_raw=True)
        for attempt in range(len(RETRY_DELAYS_S) + 1):
            try:
                out = cast(dict[str, Any], structured.invoke(messages))
            except Exception:
                if attempt == len(RETRY_DELAYS_S):
                    raise
                log.warning("gọi model thất bại, thử lại sau %ss", RETRY_DELAYS_S[attempt])
                self.sleep(RETRY_DELAYS_S[attempt])
                continue
            self.usage.add(out.get("raw"))
            parsed = out.get("parsed")
            if isinstance(parsed, schema):
                return parsed
            if isinstance(parsed, dict):
                return schema.model_validate(parsed)
            raise StoryboardError(
                f"Model không trả về {schema.__name__} hợp lệ: {out.get('parsing_error')}"
            )
        raise AssertionError("unreachable")

    # --- Các bước ---------------------------------------------------------------

    def _context(self, book: BookIdentity, kind: str) -> str:
        spoiler = (
            "Không tiết lộ kết truyện và các bước ngoặt lớn."
            if self.spoiler_free
            else "Được phép nói tới kết truyện."
        )
        return (
            f"Sách: {book.title}"
            + (f" — {book.author}" if book.author else "")
            + (f" ({book.year})" if book.year else "")
            + f"\nLoại: {'hư cấu' if kind == 'fiction' else 'phi hư cấu'}\n{spoiler}"
        )

    def outline(self, book: BookIdentity, kind: str, seed: Sequence[Chunk]) -> Outline:
        passages = "\n\n".join(c.content[:600] for c in seed[:4])
        human = (
            f"{self._context(book, kind)}\n\n"
            f"Lập dàn ý video review ~{self.settings.storyboard_minutes} phút gồm đủ 4 phần "
            "theo thứ tự hook, context, body, review_cta. Mỗi phần có 1-3 câu truy vấn để tìm "
            "trong kho nguồn."
            + (f"\n\nMột vài đoạn nguồn để nắm nội dung:\n{passages}" if passages else "")
        )
        outline = self._call(Outline, [SystemMessage(self._system), HumanMessage(human)])
        by_section = {s.section: s for s in outline.sections}
        missing = [s for s in SECTION_ORDER if s not in by_section]
        if missing:
            raise StoryboardError(f"Dàn ý thiếu phần: {', '.join(missing)}")
        outline.sections = [by_section[s] for s in SECTION_ORDER]
        return outline

    def gather(self, queries: Sequence[str]) -> list[Chunk]:
        """Retrieve theo từng query, bỏ trùng, giữ thứ tự xuất hiện đầu tiên."""
        seen: dict[str, Chunk] = {}
        for q in queries:
            for c in self.retrieve(q):
                seen.setdefault(c.id, c)
        return list(seen.values())[:MAX_PASSAGES]

    def write_section(
        self,
        book: BookIdentity,
        kind: str,
        part: OutlineSection,
        passages: Sequence[Chunk],
        next_id: int,
    ) -> list[Scene]:
        needs_cite = part.section in CITED_SECTIONS
        if needs_cite and not passages:
            raise StoryboardError(f"Không tìm được đoạn nguồn nào cho phần {part.section}")
        numbered = "\n\n".join(f"[{i}] {c.content}" for i, c in enumerate(passages, start=1))
        human = (
            f"{self._context(book, kind)}\n\nViết phần `{part.section}`: {part.brief}\n"
            + (
                "Mỗi cảnh phải có citation; chỉ dùng thông tin có trong các đoạn dưới đây.\n"
                if needs_cite
                else "Phần này là lời dẫn, không cần citation, không đưa dữ kiện ngoài nguồn.\n"
            )
            + f"quote tối đa {MAX_QUOTE_CHARS} ký tự, chép nguyên văn từ đoạn.\n\n"
            f"Các đoạn nguồn:\n{numbered or '(không có)'}"
        )
        messages: list[BaseMessage] = [SystemMessage(self._system), HumanMessage(human)]
        by_id = {c.id: c for c in passages}
        problems: list[str] = []
        for _ in range(self.settings.storyboard_retries + 1):
            draft = self._call(SectionDraft, messages)
            scenes, problems = self._resolve(draft, part.section, passages, by_id, next_id)
            if not problems:
                return scenes
            messages = [
                *messages,
                AIMessage(draft.model_dump_json()),
                HumanMessage("Sửa các lỗi sau rồi viết lại cả phần:\n- " + "\n- ".join(problems)),
            ]
        raise StoryboardError(f"Phần {part.section} không qua kiểm tra citation", problems)

    def _resolve(
        self,
        draft: SectionDraft,
        section: Section,
        passages: Sequence[Chunk],
        by_id: dict[str, Chunk],
        next_id: int,
    ) -> tuple[list[Scene], list[str]]:
        scenes: list[Scene] = []
        problems: list[str] = []
        drafts = draft.scenes
        if section in CITED_SECTIONS and any(d.citations for d in drafts):
            # Cảnh dữ kiện không dẫn nguồn thì bỏ (không đoán nguồn thay model); còn cảnh có
            # citation thì phần vẫn dùng được.
            drafts = [d for d in drafts if d.citations]
        for offset, d in enumerate(drafts):
            sid = next_id + offset
            citations: list[Citation] = []
            for c in d.citations:
                if not 1 <= c.passage <= len(passages):
                    problems.append(f"Cảnh {sid}: không có đoạn [{c.passage}].")
                    continue
                chunk = passages[c.passage - 1]
                citations.append(
                    Citation(
                        source_id=str(chunk.metadata.get("source_id", "")),
                        chunk_id=chunk.id,
                        quote=trim_quote(c.quote),
                    )
                )
            scene = Scene(
                id=sid,
                section=section,
                narration_vi=d.narration_vi.strip(),
                citations=citations,
                scene_type=d.scene_type,
                on_screen_text_vi=d.on_screen_text_vi,
                mood=d.mood,
            )
            problems += scene_problems(scene, by_id)
            scenes.append(scene)
        return scenes, problems

    # --- Toàn bộ ----------------------------------------------------------------

    def write(self, book: BookIdentity, kind: Literal["fiction", "non_fiction"]) -> Storyboard:
        seed = self.gather([book.title])
        outline = self.outline(book, kind, seed)
        scenes: list[Scene] = []
        for part in outline.sections:
            passages = self.gather(part.queries)
            scenes += self.write_section(book, kind, part, passages, len(scenes) + 1)
        hook = next((s.narration_vi for s in scenes if s.section == "hook"), "")
        return Storyboard(
            book=book,
            book_category=kind,
            spoiler_free=self.spoiler_free,
            hook_vi=hook,
            characters=outline.characters[:4] if kind == "fiction" else [],
            scenes=scenes,
            style_prompt_en=outline.style_prompt_en,
            caption_vi=outline.caption_vi,
            hashtags=outline.hashtags,
            prompt_version=PROMPT_VERSION,
        )
