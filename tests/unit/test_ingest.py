import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import pytest

from book_review_api.rag.ingest import (
    IngestError,
    LocalSnapshotStore,
    chunk_section,
    estimate_tokens,
    ingest_source,
    normalize_text,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
HTML_PAGES = {
    "nha_gia_kim.html": ("Nhà giả kim", ["Tóm tắt nội dung", "Thông điệp chính"]),
    "dac_nhan_tam.html": ("Đắc nhân tâm", ["Giới thiệu", "Các nguyên tắc nổi bật", "Đánh giá"]),
    "de_men.html": (
        "Dế Mèn phiêu lưu ký",
        ["Tác giả và hoàn cảnh ra đời", "Hành trình trưởng thành"],
    ),
}
REQUIRED_META = {
    "book_id",
    "source_id",
    "url",
    "title",
    "section",
    "content_hash",
    "ingested_at",
}
FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _ingest_html(name: str, **kw: object):  # type: ignore[no-untyped-def]
    return ingest_source(
        f"https://example.vn/{name}",
        data=(FIXTURES / name).read_bytes(),
        book_id="book-1",
        now=lambda: FIXED_NOW,
        **kw,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("name", HTML_PAGES)
def test_vietnamese_html_pages(name: str) -> None:
    title, sections = HTML_PAGES[name]
    docs = _ingest_html(name)
    text = "\n".join(d.page_content for d in docs)

    assert [d.metadata["section"] for d in docs] == sections
    for d in docs:
        assert REQUIRED_META <= d.metadata.keys()
        assert d.metadata["title"] == title
        assert d.metadata["url"] == f"https://example.vn/{name}"
        assert d.metadata["book_id"] == "book-1"
        assert d.metadata["ingested_at"] == FIXED_NOW.isoformat()
        assert "user_id" not in d.metadata  # trang công khai
        assert unicodedata.is_normalized("NFC", d.page_content)
    for junk in ("QUẢNG CÁO", "Đăng nhập", "Bài viết liên quan", "© 2026", "dataLayer"):
        assert junk not in text


def test_ingest_is_deterministic_per_source() -> None:
    a = _ingest_html("de_men.html")
    b = _ingest_html("de_men.html")
    assert [d.metadata["content_hash"] for d in a] == [d.metadata["content_hash"] for d in b]
    assert a[0].metadata["source_id"] == b[0].metadata["source_id"]


def test_pdf_masks_pii() -> None:
    docs = ingest_source(FIXTURES / "sample.pdf", user_id="u1", book_id="b")
    text = "\n".join(d.page_content for d in docs)
    assert "Sapiens" in text and "khoa học" in text
    assert "[EMAIL]" in text and "[PHONE]" in text and "[CARD]" in text
    for leaked in ("lan.nguyen@example.com", "0912", "4111"):
        assert leaked not in text
    assert docs[0].metadata["user_id"] == "u1"
    assert docs[0].metadata["pii_masked"] == 3
    assert docs[0].metadata["title"] == "Ghi chú đọc sách Sapiens"


def test_docx_sections_and_pii() -> None:
    docs = ingest_source(FIXTURES / "sample.docx", user_id="u1")
    assert [d.metadata["section"] for d in docs] == ["Tóm tắt", "Liên hệ"]
    text = "\n".join(d.page_content for d in docs)
    assert "lan.nguyen@example.com" not in text and "[EMAIL]" in text


def test_txt_upload_normalizes_to_nfc() -> None:
    decomposed = unicodedata.normalize("NFD", "Tiếng Việt   có   dấu\r\n\r\n\r\n\r\nĐoạn hai")
    docs = ingest_source("note.txt", data=decomposed.encode(), user_id="u1")
    assert len(docs) == 1
    assert docs[0].page_content == "Tiếng Việt có dấu\n\nĐoạn hai"
    assert unicodedata.is_normalized("NFC", docs[0].page_content)


def test_snapshot_saved(tmp_path: Path) -> None:
    store = LocalSnapshotStore(tmp_path)
    docs = _ingest_html("nha_gia_kim.html", snapshot_store=store)
    saved = tmp_path / "sources" / f"{docs[0].metadata['source_id']}.txt"
    assert "Nhà giả kim kể về Santiago" in saved.read_text(encoding="utf-8")


def test_url_fetch_failure() -> None:
    with pytest.raises(IngestError):
        ingest_source("https://example.vn/x", fetch=lambda _url: None)


def test_unsupported_format() -> None:
    with pytest.raises(IngestError):
        ingest_source("slides.pptx", data=b"x")


def test_normalize_text() -> None:
    assert normalize_text("a   b\x00\n\n\n\nc ") == "a b\n\nc"


def _paragraphs(n: int, words: int = 60) -> str:
    return "\n\n".join(" ".join(f"p{i}w{j}" for j in range(words)) for i in range(n))


def test_chunk_size_and_overlap() -> None:
    chunks = chunk_section(_paragraphs(30))
    assert len(chunks) > 1
    for c in chunks[:-1]:
        assert 500 <= estimate_tokens(c) <= 800 + 80
    # Chunk sau mở đầu bằng đuôi của chunk trước (~80 token).
    tail = chunks[0].split()[-5:]
    assert chunks[1].split()[:53][-5:] == tail or " ".join(tail) in chunks[1]
    covered = {w for c in chunks for w in c.split()}
    assert len(covered) == 30 * 60  # không mất từ nào


def test_long_paragraph_is_split() -> None:
    body = " ".join(f"w{i}" for i in range(2000))
    chunks = chunk_section(body)
    assert len(chunks) >= 3
    assert all(estimate_tokens(c) <= 800 + 80 for c in chunks)


def test_short_tail_merges_into_previous() -> None:
    chunks = chunk_section(_paragraphs(9) + "\n\nđuôi ngắn")
    assert chunks[-1].endswith("đuôi ngắn")
    assert estimate_tokens(chunks[-1]) > 120
