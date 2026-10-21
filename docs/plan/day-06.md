# Ngày 6: RAG: embeddings, pgvector, incremental indexing

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Lưu chunk vào pgvector với index HNSW, nạp lại cùng nguồn không tạo chunk trùng.

## Phụ thuộc / chuẩn bị

- Ngày 5

## Công việc

### Embeddings

- [x] `providers/llm_gemini.py`: embedding model đa ngôn ngữ đặt trong config.
- [ ] Đo chi phí và độ trễ embed cho 100 chunk: script `scripts/measure_embeddings.py` đã có, chờ chạy với key thật.

### Vector store

- [x] `langchain-postgres` `PGVector`, migration tạo index HNSW.
- [x] RLS cho chunk riêng tư theo `user_id`, chunk công khai dùng chung theo `book_id`.

### Incremental

- [x] LangChain Indexing API: `index()` + `SQLRecordManager`, chế độ `incremental`.
- [x] Hash không đổi thì bỏ qua, hash đổi thì xóa chunk cũ của nguồn đó rồi nạp lại.

### Test

- [x] Nạp cùng nguồn 2 lần: số chunk không đổi. Đổi nội dung: chunk cũ bị thay.

## Đầu ra

- Module index hoàn chỉnh
- Test incremental indexing

## Tiêu chí hoàn thành

- [x] Nạp lại cùng nguồn không tạo chunk trùng
- [x] Kho tri thức theo sách dùng lại được giữa các lần chạy

---

[← Ngày 5](day-05.md) · [Mục lục](README.md) · [Ngày 7 →](day-07.md)
