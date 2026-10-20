# Ngày 5: RAG: ingestion

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Nạp một nguồn (URL, PDF, TXT, DOCX) thành các chunk sạch, có metadata đầy đủ và snapshot văn bản gốc.

## Phụ thuộc / chuẩn bị

- Ngày 4 (bảng documents, storage)

## Công việc

### Làm sạch

- [ ] `rag/ingest.py`: lấy nội dung chính bằng `trafilatura`, bỏ menu, quảng cáo.
- [ ] Đọc PDF, DOCX, TXT người dùng tải lên.
- [ ] Chuẩn hóa Unicode NFC, gom khoảng trắng.

### Chunking

- [ ] Chia 500–800 token, overlap ~80 token, giữ tiêu đề mục làm metadata `section`.
- [ ] Metadata mỗi chunk: `book_id`, `source_id`, `url`, `title`, `section`, `content_hash`, `ingested_at`, `user_id` (nếu riêng tư).

### Snapshot & PII

- [ ] Lưu `sources/<source_id>.txt` lên storage.
- [ ] `rag/pii.py`: quét và che email, số điện thoại, số thẻ trong tài liệu tải lên trước khi chunk.

### Test

- [ ] Test với 3 trang mẫu tiếng Việt (lưu HTML cố định trong `tests/fixtures`), 1 PDF, 1 DOCX.

## Đầu ra

- Hàm `ingest_source(url|file) -> list[Document]`
- Fixture và unit test

## Tiêu chí hoàn thành

- [ ] Văn bản sạch, đúng NFC, chunk có đủ metadata
- [ ] PII trong tài liệu mẫu đã bị che

---

[← Ngày 4](day-04.md) · [Mục lục](README.md) · [Ngày 6 →](day-06.md)
