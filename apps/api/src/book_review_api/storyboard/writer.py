"""Viết storyboard từ các đoạn truy xuất: dàn ý -> query từng phần -> retrieve -> viết từng phần.

Mọi lần gọi model dùng structured output. Citation do model chọn theo số thứ tự đoạn
(`[1]`, `[2]`...) rồi được đổi thành `chunk_id`/`source_id` thật, nên model không thể bịa id.
Phần nào vi phạm validator thì được gửi lại kèm danh sách lỗi, tối đa `storyboard_retries` lần.
"""

import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import Literal, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from book_review_api.config import Settings, get_settings
from book_review_api.prompt_loader import ACTIVE_PROMPTS
from book_review_api.prompt_loader import load_prompt as _load_prompt
from book_review_api.providers.structured import (
    StructuredOutputError,
    Usage,
    call_structured,
)
from book_review_api.rag.retrieve import Chunk
from book_review_api.storyboard.duration import estimate_seconds, syllables_for
from book_review_api.storyboard.schema import (
    CITED_SECTIONS,
    MAX_QUOTE_CHARS,
    SECONDS_PER_SCENE,
    SECTION_ORDER,
    BookIdentity,
    Character,
    Citation,
    Scene,
    SceneType,
    Section,
    Storyboard,
    section_max_scenes,
)
from book_review_api.storyboard.schema import (
    SECTION_MAX_SCENES as SECTION_DEFAULT_MAX,
)
from book_review_api.storyboard.validate import scene_problems

log = logging.getLogger(__name__)

PROMPT_VERSION = ACTIVE_PROMPTS["storyboard"]

# Số đoạn tối đa đưa cho model viết một phần.
MAX_PASSAGES = 12
# Trần số cảnh trong một lần trả lời của model. Phải lớn hơn số cảnh của phần dài nhất
# (`body` 27 cảnh với video 5 phút); trần cũ 6 chặn video 3 phút ở tối đa 19 cảnh.
MAX_DRAFT_SCENES = 30
# Phần ngắn hơn tỉ lệ này của mục tiêu (số cảnh hoặc thời lượng) thì bị yêu cầu viết lại.
# Cùng ngưỡng với cờ `SHORT_SCRIPT` của cả kịch bản: phần nào cũng đạt thì tổng cũng đạt.
MIN_SCENE_RATIO = 0.9
MIN_SECONDS_RATIO = 0.9
# Cả kịch bản ngắn hơn tỉ lệ này của thời lượng mục tiêu thì gắn cờ `SHORT_SCRIPT`.
SHORT_SCRIPT_RATIO = 0.9
# Số ký tự tối đa của mỗi cảnh đã viết đưa vào prompt phần sau (để không lặp ý).
PREVIOUS_SCENE_CHARS = 160

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
    scenes: list[SceneDraft] = Field(min_length=1, max_length=MAX_DRAFT_SCENES)


_MARKER_RE = re.compile(r"\s*\[\d+\]")


def clean_narration(text: str) -> str:
    """Bỏ dấu tham chiếu `[1]` model hay chép từ đoạn nguồn vào lời đọc."""
    return _MARKER_RE.sub("", text).strip()


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
    return _load_prompt(PROMPT_VERSION)


def salvage_scenes(scenes: Sequence[Scene], by_id: dict[str, Chunk], next_id: int) -> list[Scene]:
    """Giữ các trích dẫn hợp lệ; cảnh phần context/body không còn trích nào thì bỏ. Đánh số lại."""
    kept: list[Scene] = []
    for scene in scenes:
        good = [
            c
            for c in scene.citations
            if not scene_problems(scene.model_copy(update={"citations": [c]}), by_id)
        ]
        fixed = scene.model_copy(update={"citations": good})
        if scene_problems(fixed, by_id):
            continue
        kept.append(fixed.model_copy(update={"id": next_id + len(kept)}))
    return kept


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
        try:
            return call_structured(self.model, schema, messages, self.usage, self.sleep)
        except StructuredOutputError as e:
            raise StoryboardError(str(e)) from e

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

    def _max_scenes(self) -> dict[str, int]:
        return section_max_scenes(self.settings.storyboard_minutes)

    def _is_long(self, section: str) -> bool:
        """Video dài hơn mặc định (~1 phút): phần này cần nhiều cảnh hơn quy tắc chung."""
        return self._max_scenes()[section] > SECTION_DEFAULT_MAX[section]

    def _min_scenes(self, section: str) -> int:
        return max(1, round(self._max_scenes()[section] * MIN_SCENE_RATIO))

    def _scene_count_hint(self, section: str) -> str:
        """Ghi đè quy tắc số cảnh mặc định (video ~45 giây) khi người dùng chọn video dài hơn."""
        if not self._is_long(section):
            return ""
        limit = self._max_scenes()[section]
        words = syllables_for(SECONDS_PER_SCENE)
        return (
            f"Video dài ~{self.settings.storyboard_minutes} phút nên phần này viết ĐÚNG {limit} "
            f"cảnh (không ít hơn {self._min_scenes(section)}), mỗi cảnh 2-3 câu, khoảng {words} "
            f"từ, đọc được khoảng {SECONDS_PER_SCENE:g} giây. Không lặp ý, không bịa thêm ngoài "
            "nguồn. Chia nhỏ ý trong nguồn thành nhiều cảnh thay vì gộp; một đoạn nguồn có thể "
            "cho nhiều cảnh.\n"
        )

    def _shortfall(self, section: str, scenes: Sequence[Scene]) -> str | None:
        """Lỗi gửi lại cho model khi phần viết ra ngắn hơn mục tiêu (số cảnh hoặc thời lượng)."""
        if not self._is_long(section):
            return None
        limit = self._max_scenes()[section]
        want_s = limit * SECONDS_PER_SCENE
        have_s = estimate_seconds(s.narration_vi for s in scenes)
        if len(scenes) >= self._min_scenes(section) and have_s >= want_s * MIN_SECONDS_RATIO:
            return None
        return (
            f"Phần {section} mới có {len(scenes)} cảnh, đọc khoảng {have_s:.0f} giây; cần "
            f"{limit} cảnh, khoảng {want_s:.0f} giây. Viết lại cả phần cho đủ: tách ý dài thành "
            f"nhiều cảnh, mỗi cảnh 2-3 câu khoảng {syllables_for(SECONDS_PER_SCENE)} từ, vẫn chỉ "
            "dùng thông tin trong các đoạn nguồn."
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

    def gather(self, queries: Sequence[str], limit: int = MAX_PASSAGES) -> list[Chunk]:
        """Retrieve theo từng query, bỏ trùng, giữ thứ tự xuất hiện đầu tiên."""
        seen: dict[str, Chunk] = {}
        for q in queries:
            for c in self.retrieve(q):
                seen.setdefault(c.id, c)
        return list(seen.values())[:limit]

    def write_section(
        self,
        book: BookIdentity,
        kind: str,
        part: OutlineSection,
        passages: Sequence[Chunk],
        next_id: int,
        previous: Sequence[Scene] = (),
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
            + self._scene_count_hint(part.section)
            + f"quote tối đa {MAX_QUOTE_CHARS} ký tự, chép nguyên văn từ đoạn.\n\n"
            + _previous_block(previous)
            + f"Các đoạn nguồn:\n{numbered or '(không có)'}"
        )
        messages: list[BaseMessage] = [SystemMessage(self._system), HumanMessage(human)]
        by_id = {c.id: c for c in passages}
        problems: list[str] = []
        # Bản hợp lệ dài nhất; viết lại vẫn thiếu cảnh thì dùng bản này thay vì thất bại.
        best: list[Scene] | None = None
        scenes: list[Scene] = []
        for _ in range(self.settings.storyboard_retries + 1):
            draft = self._call(SectionDraft, messages)
            scenes, problems = self._resolve(draft, part.section, passages, by_id, next_id)
            if not problems:
                if best is None or _seconds(scenes) > _seconds(best):
                    best = scenes
                short = self._shortfall(part.section, scenes)
                if short is None:
                    return scenes
                log.info("storyboard: %s", short)
                problems = [short]
            messages = [
                *messages,
                AIMessage(draft.model_dump_json()),
                HumanMessage("Sửa các lỗi sau rồi viết lại cả phần:\n- " + "\n- ".join(problems)),
            ]
        if best is not None:
            return best
        # Viết lại hết lượt vẫn còn trích sai: bỏ trích sai, bỏ cảnh không còn trích nào, giữ phần
        # còn lại thay vì huỷ cả kịch bản.
        kept = salvage_scenes(scenes, by_id, next_id)
        if kept:
            log.warning("storyboard: phần %s bỏ cảnh trích sai: %s", part.section, problems)
            return kept
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
        drafts = drafts[: self._max_scenes()[section]]
        for offset, d in enumerate(drafts):
            sid = next_id + offset
            citations: list[Citation] = []
            for c in d.citations:
                if not 1 <= c.passage <= len(passages):
                    if section in CITED_SECTIONS:
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
                narration_vi=clean_narration(d.narration_vi),
                citations=citations,
                scene_type=d.scene_type,
                on_screen_text_vi=d.on_screen_text_vi,
                mood=d.mood,
            )
            found = scene_problems(scene, by_id)
            if found and section not in CITED_SECTIONS:
                # hook/review_cta không cần citation: trích sai thì bỏ trích, giữ lời dẫn.
                scene.citations = []
                found = scene_problems(scene, by_id)
            problems += found
            scenes.append(scene)
        return scenes, problems

    # --- Toàn bộ ----------------------------------------------------------------

    def write(self, book: BookIdentity, kind: Literal["fiction", "non_fiction"]) -> Storyboard:
        seed = self.gather([book.title])
        outline = self.outline(book, kind, seed)
        scenes: list[Scene] = []
        for part in outline.sections:
            # Phần dài cần nhiều đoạn nguồn hơn, nếu không model hết ý và viết ít cảnh.
            passages = self.gather(
                part.queries, max(MAX_PASSAGES, 2 * self._max_scenes()[part.section])
            )
            scenes += self.write_section(book, kind, part, passages, len(scenes) + 1, scenes)
        hook = next((s.narration_vi for s in scenes if s.section == "hook"), "")
        target_s = float(self.settings.storyboard_minutes * 60)
        estimated_s = _seconds(scenes)
        flags: list[str] = []
        if any(self._is_long(s) for s in SECTION_ORDER) and estimated_s < (
            target_s * SHORT_SCRIPT_RATIO
        ):
            log.warning(
                "storyboard ngắn: %d cảnh, ~%.0f giây, mục tiêu %.0f giây",
                len(scenes),
                estimated_s,
                target_s,
            )
            flags.append("SHORT_SCRIPT")
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
            target_seconds=target_s,
            estimated_seconds=round(estimated_s, 1),
            flags=flags,
        )


def _seconds(scenes: Sequence[Scene]) -> float:
    return estimate_seconds(s.narration_vi for s in scenes)


def _previous_block(previous: Sequence[Scene]) -> str:
    """Các cảnh đã viết ở phần trước, để phần sau không kể lại (vd giới thiệu nhân vật hai lần)."""
    if not previous:
        return ""
    lines = "\n".join(f"- ({s.section}) {s.narration_vi[:PREVIOUS_SCENE_CHARS]}" for s in previous)
    return f"Các cảnh đã viết ở phần trước, KHÔNG lặp lại ý trong đó:\n{lines}\n\n"
