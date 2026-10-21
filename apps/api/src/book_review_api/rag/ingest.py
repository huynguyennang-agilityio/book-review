"""Nạp một nguồn (URL, PDF, DOCX, TXT) thành các chunk sạch có metadata đầy đủ."""

import hashlib
import io
import re
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import trafilatura
from docx import Document as DocxFile
from pypdf import PdfReader

from book_review_api.rag.pii import mask_pii

TARGET_MIN_TOKENS = 500
TARGET_MAX_TOKENS = 800
OVERLAP_TOKENS = 80
# Tiếng Việt: mỗi âm tiết là một "từ" và tokenizer LLM thường tách thành ~1,5 token.
TOKENS_PER_WORD = 1.5

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*$")
_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt"}


@dataclass(frozen=True)
class Document:
    """Một chunk văn bản kèm metadata (cùng dạng với Document của LangChain)."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SnapshotStore(Protocol):
    def put(self, path: str, data: bytes) -> None: ...


class LocalSnapshotStore:
    """Ghi snapshot vào thư mục local; bản Supabase Storage cắm cùng giao diện `put`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, path: str, data: bytes) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


class IngestError(ValueError):
    pass


def estimate_tokens(text: str) -> int:
    return round(len(text.split()) * TOKENS_PER_WORD)


# --- Làm sạch -----------------------------------------------------------------


def normalize_text(text: str) -> str:
    """NFC, bỏ ký tự điều khiển, gom khoảng trắng, giữ ranh giới đoạn."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c) != "Cc")
    text = text.replace(" ", " ").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_html(html: str, url: str | None = None) -> tuple[str, str | None]:
    """Nội dung chính (markdown, giữ tiêu đề mục) và title; bỏ menu, quảng cáo."""
    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not text:
        raise IngestError("Không trích được nội dung chính từ trang")
    meta = trafilatura.extract_metadata(html, default_url=url)
    return text, (meta.title if meta else None)


def extract_pdf(data: bytes) -> tuple[str, str | None]:
    reader = PdfReader(io.BytesIO(data))
    text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    title = reader.metadata.title if reader.metadata else None
    return text, title


def extract_docx(data: bytes) -> tuple[str, str | None]:
    doc = DocxFile(io.BytesIO(data))
    lines: list[str] = []
    for p in doc.paragraphs:
        if not p.text.strip():
            lines.append("")
            continue
        style = p.style.name if p.style is not None and p.style.name else ""
        if style == "Title":
            lines.append(f"# {p.text}")
        elif style.startswith("Heading "):
            level = style.removeprefix("Heading ")
            lines.append(f"{'#' * (int(level) if level.isdigit() else 1)} {p.text}")
        else:
            lines.append(p.text)
    return "\n".join(lines), doc.core_properties.title or None


def extract_txt(data: bytes) -> tuple[str, str | None]:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(enc), None
        except UnicodeDecodeError:
            continue
    raise IngestError("File TXT không phải UTF-8")


# --- Chunking -----------------------------------------------------------------


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    """Tách theo dòng tiêu đề markdown; mỗi phần giữ tên mục gần nhất."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            sections.append((m.group(1).strip(), []))
        else:
            sections[-1][1].append(line)
    out = [(name, "\n".join(lines).strip()) for name, lines in sections]
    return [(name, body) for name, body in out if body]


def _split_long(paragraph: str, max_words: int) -> list[str]:
    words = paragraph.split()
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def chunk_section(
    body: str,
    *,
    max_tokens: int = TARGET_MAX_TOKENS,
    min_tokens: int = TARGET_MIN_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Gom đoạn văn tới ~max_tokens; chunk sau lặp lại ~overlap_tokens cuối chunk trước."""
    max_words = int(max_tokens / TOKENS_PER_WORD)
    min_words = int(min_tokens / TOKENS_PER_WORD)
    overlap_words = int(overlap_tokens / TOKENS_PER_WORD)

    units: list[str] = []
    for para in (p.strip() for p in body.split("\n\n")):
        if para:
            units.extend(_split_long(para, max_words) if len(para.split()) > max_words else [para])

    chunks: list[str] = []
    current: list[str] = []
    count = 0
    carried = 0  # số từ lặp lại từ chunk trước (overlap), không tính là nội dung mới
    for unit in units:
        n = len(unit.split())
        if current and count + n > max_words and count >= min_words:
            joined = "\n\n".join(current)
            chunks.append(joined)
            tail = " ".join(joined.split()[-overlap_words:])
            carried = len(tail.split())
            current, count = [tail], carried
        current.append(unit)
        count += n
    if current:
        # Phần đuôi quá ngắn thì gộp vào chunk trước thay vì tạo chunk nhỏ lẻ.
        if chunks and count - carried < min_words // 4:
            chunks[-1] += "\n\n" + "\n\n".join(current[1:])
        else:
            chunks.append("\n\n".join(current))
    return chunks


def chunk_text(text: str) -> list[tuple[str | None, str]]:
    """Trả về danh sách (section, nội dung chunk)."""
    return [
        (section, chunk) for section, body in _split_sections(text) for chunk in chunk_section(body)
    ]


# --- Điểm vào -----------------------------------------------------------------


def _sha256(data: str | bytes) -> str:
    raw = data.encode() if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _is_url(source: str | Path) -> bool:
    return isinstance(source, str) and source.lower().startswith(("http://", "https://"))


def ingest_source(
    source: str | Path,
    *,
    data: bytes | None = None,
    book_id: str | None = None,
    user_id: str | None = None,
    source_id: str | None = None,
    snapshot_store: SnapshotStore | None = None,
    fetch: Callable[[str], str | None] = trafilatura.fetch_url,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[Document]:
    """Nạp URL hoặc file thành các chunk.

    `data` là nội dung đã có sẵn (HTML của URL hoặc byte của file tải lên). PII chỉ bị che với
    file tải lên; trang web công khai giữ nguyên. Snapshot văn bản sạch lưu ở
    `sources/<source_id>.txt` nếu có `snapshot_store`.
    """
    uploaded = not _is_url(source)
    if uploaded:
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix not in _UPLOAD_SUFFIXES:
            raise IngestError(f"Định dạng không hỗ trợ: {suffix or path.name}")
        raw = data if data is not None else path.read_bytes()
        extractor = {".pdf": extract_pdf, ".docx": extract_docx, ".txt": extract_txt}[suffix]
        text, title = extractor(raw)
        url = None
        ref = path.name
        title = title or path.stem
    else:
        url = str(source)
        if data is None:
            html = fetch(url)
            if html is None:
                raise IngestError(f"Không tải được trang: {url}")
        else:
            html = data.decode("utf-8", errors="replace")
        text, title = extract_html(html, url)
        ref = url

    text = normalize_text(text)
    pii_masked = 0
    if uploaded:
        masked = mask_pii(text)
        text, pii_masked = masked.text, masked.total
    if not text:
        raise IngestError("Nguồn không có nội dung")

    source_hash = _sha256(text)
    if source_id is None:
        source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id or ''}|{ref}"))
    if snapshot_store is not None:
        snapshot_store.put(f"sources/{source_id}.txt", text.encode())

    ingested_at = now().isoformat()
    docs: list[Document] = []
    for index, (section, content) in enumerate(chunk_text(text)):
        metadata: dict[str, Any] = {
            "book_id": book_id,
            "source_id": source_id,
            "url": url,
            "title": title,
            "section": section,
            "content_hash": _sha256(content),
            "source_hash": source_hash,
            "chunk_index": index,
            "token_count": estimate_tokens(content),
            "ingested_at": ingested_at,
        }
        if uploaded:
            metadata["user_id"] = user_id
            metadata["pii_masked"] = pii_masked
        docs.append(Document(page_content=content, metadata=metadata))
    return docs
