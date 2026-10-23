"""Tab "Từ bài review có sẵn": kiểm tra bài review người dùng dán và node `ingest_review`.

Bài có 3 ô: hook (tuỳ chọn), ý chính (bắt buộc), nhận xét (tuỳ chọn). Lời đọc giữ nguyên văn
nên thời lượng video suy từ độ dài bài; `precheck` chặn bài quá ngắn hoặc quá dài trước khi tốn
tiền. Xem `docs/plan/review-text/`.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from langgraph.config import get_config

from book_review_api.config import Settings, get_settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate, node
from book_review_api.graph.nodes.precheck import find_excluded_keyword
from book_review_api.graph.state import BookReviewState, UserReview
from book_review_api.rag.index import chunk_key, to_langchain
from book_review_api.rag.ingest import Document, ingest_text, normalize_text
from book_review_api.rag.pii import mask_pii
from book_review_api.storyboard.duration import count_syllables, estimate_seconds
from book_review_api.storyboard.review_meta import (
    MAX_CHARACTERS,
    MAX_HASHTAGS,
    MetaWriter,
    ReviewMeta,
    SceneMeta,
    default_meta,
    on_screen_text,
)
from book_review_api.storyboard.schema import (
    BookIdentity,
    Character,
    Citation,
    Scene,
    Storyboard,
)
from book_review_api.storyboard.validate import fold_quote
from book_review_api.storyboard.verbatim import (
    SceneText,
    paragraphs,
    split_review_into_scenes,
    split_sentences,
    verbatim_problems,
)
from book_review_api.storyboard.writer import trim_quote

log = logging.getLogger(__name__)

MIN_MAIN_WORDS = 100
MAX_SECONDS = 300.0
# Hook dài hơn ~5 giây thì cảnh báo, không chặn.
HOOK_MAX_WORDS = 20
# Giới hạn cứng mỗi ô để không nhận văn bản khổng lồ (5 phút đọc chỉ ~1.100 từ).
MAX_FIELD_CHARS = 20_000
FIELDS = ("hook", "main", "comment")
FIELD_LABELS = {"hook": "Hook", "main": "Ý chính", "comment": "Nhận xét"}
PROMPT_VERSION = "review_text_v1"


class ReviewInputError(ValueError):
    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def is_user_review(state: Mapping[str, Any]) -> bool:
    return (state.get("options") or {}).get("source") == "user_review"


def _clean(text: object) -> tuple[str | None, int]:
    if not isinstance(text, str):
        return None, 0
    masked = mask_pii(normalize_text(text[:MAX_FIELD_CHARS]))
    return masked.text or None, masked.total


def clean_user_review(raw: Mapping[str, Any] | None) -> UserReview:
    """Làm sạch và che PII ba ô, kiểm độ dài. Lỗi thì ném `ReviewInputError` với mã lỗi."""
    if not isinstance(raw, Mapping):
        raise ReviewInputError(ErrorCode.VALIDATION_ERROR)
    cleaned: dict[str, str | None] = {}
    pii = 0
    for field in FIELDS:
        cleaned[field], found = _clean(raw.get(field))
        pii += found
    main = cleaned["main"]
    if not main or count_syllables(main) < MIN_MAIN_WORDS:
        raise ReviewInputError(ErrorCode.REVIEW_TOO_SHORT)
    if review_seconds(cleaned) > MAX_SECONDS:
        raise ReviewInputError(ErrorCode.REVIEW_TOO_LONG)
    warnings: list[str] = []
    if cleaned["hook"] and count_syllables(cleaned["hook"]) > HOOK_MAX_WORDS:
        warnings.append("HOOK_LONG")
    return UserReview(
        hook=cleaned["hook"],
        main=main,
        comment=cleaned["comment"],
        warnings=warnings,
        pii_masked=pii,
    )


def review_seconds(review: Mapping[str, str | None]) -> float:
    """Thời lượng đọc ước tính của cả bài, chia cảnh và đọc số thành chữ y như `ingest_review`
    nên khớp `estimated_seconds` của storyboard."""
    scenes = split_review_into_scenes(
        review.get("hook"), review.get("main") or "", review.get("comment")
    )
    return estimate_seconds(s.narration for s in scenes)


def excluded_keyword(review: Mapping[str, Any]) -> str | None:
    """Từ khoá thể loại không hỗ trợ (tiên hiệp, kiếm hiệp...) trong nội dung bài."""
    for field in FIELDS:
        text = review.get(field)
        if isinstance(text, str) and (found := find_excluded_keyword(text)):
            return found
    return None


def precheck_review(state: BookReviewState) -> NodeUpdate:
    """Phần kiểm tra riêng của tab review, gọi từ `precheck`. Rỗng nghĩa là hợp lệ, không đổi."""
    try:
        review = clean_user_review(state.get("user_review"))
    except ReviewInputError as e:
        return {"status": "rejected", "error_code": e.code.value}
    if excluded_keyword(review):
        return {"status": "rejected", "error_code": ErrorCode.GENRE_EXCLUDED.value}
    return {"user_review": review}


# Nạp chunk của bài vào kho vector (pgvector ở bản chạy thật), kèm user_id chủ bài.
IndexDocs = Callable[[Sequence[Document], str | None], None]


class VerbatimError(RuntimeError):
    """Lời đọc lệch văn bản gốc: lỗi code chia cảnh, không phải lỗi của người dùng."""


def review_hash(review: Mapping[str, Any]) -> str:
    raw = "\x1f".join(str(review.get(f) or "") for f in FIELDS)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def review_documents(
    review: Mapping[str, Any], title: str, book_id: str, user_id: str | None
) -> list[Document]:
    """Mỗi ô là một nguồn `user_review:<hash>:<ô>`; chunk mang `user_id` nên RLS giữ riêng tư."""
    digest = review_hash(review)
    docs: list[Document] = []
    for f in FIELDS:
        lines = paragraphs(review.get(f) or "")
        if not lines:
            continue
        for d in ingest_text(
            "\n".join(lines),
            title=f"{title} · {FIELD_LABELS[f]}",
            book_id=book_id,
            source_id=f"user_review:{digest}:{f}",
        ):
            docs.append(Document(d.page_content, {**d.metadata, "user_id": user_id}))
    return docs


def _citation(scene: SceneText, chunks: Sequence[tuple[str, Document]]) -> Citation | None:
    """Trích chính câu của cảnh, từ chunk chứa nó (thử cả cảnh rồi câu đầu, phòng cảnh nằm vắt
    qua hai chunk)."""
    sentences = split_sentences(scene.text)
    for quote in dict.fromkeys([trim_quote(scene.text), trim_quote(sentences[0])]):
        folded = fold_quote(quote)
        for chunk_id, doc in chunks:
            if folded in fold_quote(doc.page_content):
                return Citation(
                    source_id=str(doc.metadata["source_id"]), chunk_id=chunk_id, quote=quote
                )
    return None


def _merge_scene(
    sid: int, text: SceneText, meta: SceneMeta | None, citation: Citation | None
) -> Scene:
    return Scene(
        id=sid,
        section=text.section,
        narration_vi=text.narration,
        citations=[citation] if citation else [],
        scene_type=meta.scene_type if meta else ("title" if text.section == "hook" else "metaphor"),
        on_screen_text_vi=on_screen_text(meta.on_screen_text_vi) if meta else None,
        mood=(meta.mood.strip() if meta else "") or "calm",
        faithfulness=1.0,
        tts_changes=text.changes,
    )


def build_review_storyboard(
    review: Mapping[str, Any],
    book: BookIdentity,
    meta: ReviewMeta,
    texts: Sequence[SceneText],
    docs: Sequence[Document],
) -> Storyboard:
    chunks = [(chunk_key(to_langchain(d)), d) for d in docs]
    by_id = {m.id: m for m in meta.scenes}
    scenes = [
        _merge_scene(i, t, by_id.get(i), _citation(t, chunks)) for i, t in enumerate(texts, 1)
    ]
    fiction = meta.kind == "fiction"
    flags = [w for w in review.get("warnings") or [] if isinstance(w, str)]
    return Storyboard(
        source="user_review",
        book=book,
        book_category=meta.kind,
        # Nội dung là bài của người dùng, web không kiểm được có tiết lộ kết truyện hay không.
        spoiler_free=False,
        hook_vi=next((s.narration_vi for s in scenes if s.section == "hook"), ""),
        characters=[
            Character(
                name=c.name,
                description_en=c.description_en,
                appearance_guessed=c.appearance_guessed,
            )
            for c in meta.characters[:MAX_CHARACTERS]
            if c.name.strip()
        ]
        if fiction
        else [],
        scenes=scenes,
        style_prompt_en=meta.style_prompt_en,
        caption_vi=meta.caption_vi,
        hashtags=[h if h.startswith("#") else f"#{h}" for h in meta.hashtags[:MAX_HASHTAGS] if h],
        prompt_version=PROMPT_VERSION,
        # Độ dài theo bài, không có mục tiêu do người dùng chọn.
        target_seconds=None,
        estimated_seconds=round(estimate_seconds(s.narration_vi for s in scenes), 1),
        flags=flags,
    )


def research_for(
    book: BookIdentity, kind: str, book_id: str, docs: Sequence[Document]
) -> dict[str, Any]:
    """`state.research` cùng dạng research agent trả, để các node sau không phải phân biệt."""
    titles = dict.fromkeys(str(d.metadata.get("title") or "") for d in docs)
    return {
        "book": book.model_dump(),
        "kind": kind,
        "genre": "",
        "candidates": [],
        "low_confidence": False,
        "sources": [{"url": "", "title": t} for t in titles if t],
        "notes": "Bài review có sẵn của người dùng",
        "book_id": book_id,
    }


def _user_id() -> str | None:
    try:
        user_id = get_config().get("configurable", {}).get("user_id")
    except RuntimeError:  # chạy ngoài graph (test, script)
        return None
    return str(user_id) if user_id else None


def make_ingest_review_node(
    meta_writer: MetaWriter | None = None,
    index: IndexDocs | None = None,
    settings: Settings | None = None,
) -> NodeFn:
    """Chia cảnh nguyên văn, nạp bài vào RAG, gắn metadata, ra `research` và `storyboard`.

    Không có `meta_writer` (test khung) thì dùng metadata mặc định; gọi model lỗi cũng vậy,
    kèm cờ `META_DEFAULT` để người duyệt biết loại cảnh, chữ trên màn hình là mặc định."""

    @node
    def ingest_review(state: BookReviewState) -> NodeUpdate:
        review = state.get("user_review")
        if not review or not review.get("main"):
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        hook, main, comment = review.get("hook"), review["main"], review.get("comment")
        texts = split_review_into_scenes(hook, main, comment)
        if problems := verbatim_problems(hook, main, comment, texts):
            log.error("chia cảnh lệch nguyên văn: %s", problems)
            return {"status": "failed", "error_code": ErrorCode.INTERNAL_ERROR.value}
        book_in = state.get("book") or {"title": ""}
        book = BookIdentity(title=book_in.get("title") or "", author=book_in.get("author"))
        user_id = _user_id()
        book_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"user_review|{user_id}|{review_hash(review)}")
        )
        docs = review_documents(review, book.title, book_id, user_id)
        if index is not None:
            index(docs, user_id)
        listed = [(i, t.section, t.text) for i, t in enumerate(texts, 1)]
        update: NodeUpdate = {}
        meta = default_meta(listed)
        extra_flags: list[str] = []
        if meta_writer is not None:
            try:
                meta, usage = meta_writer(book.title, listed)
            except Exception:  # noqa: BLE001
                log.warning("không gắn được metadata bằng model, dùng mặc định", exc_info=True)
                extra_flags.append("META_DEFAULT")
            else:
                cfg = settings or get_settings()
                update["cost"] = {
                    "usd": usage.usd_for(cfg),
                    "input_tokens": float(usage.input_tokens),
                    "output_tokens": float(usage.output_tokens),
                }
                if not meta.genre_ok:
                    return {
                        **update,
                        "status": "rejected",
                        "error_code": ErrorCode.GENRE_EXCLUDED.value,
                    }
        storyboard = build_review_storyboard(review, book, meta, texts, docs)
        storyboard.flags += extra_flags
        return {
            **update,
            "research": research_for(book, meta.kind, book_id, docs),
            "storyboard": storyboard.model_dump(),
            # Lời đọc là nguyên văn (đã kiểm bằng code), không cần giám khảo LLM.
            "eval_scores": {"faithfulness": 1.0},
        }

    return ingest_review
