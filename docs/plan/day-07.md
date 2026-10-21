# Ngày 7: RAG: hybrid retrieval và rerank

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Truy xuất đúng đoạn cho câu hỏi theo từng phần kịch bản, kể cả khi hỏi bằng tên riêng tiếng Việt.

## Phụ thuộc / chuẩn bị

- Ngày 6

## Công việc

### Retrieval

- [x] `rag/retrieve.py`: vector search + full-text search của Postgres, gộp kết quả (RRF), top-k=8.
- [x] Rerank xuống 4 (reranker đặt trong config, có thể dùng LLM hoặc cross-encoder).
- [x] Luôn lọc theo `book_id`.

### Kiểm tra

- [x] Nạp nguồn cho 1 sách mẫu, soạn 5 câu hỏi mẫu (hook, bối cảnh, bài học, kết truyện, tên nhân vật) cùng đoạn đúng mong đợi.
- [x] Test tự động kiểm tra đoạn đúng nằm trong top 4.

## Đầu ra

- Hàm `retrieve(book_id, query) -> list[Chunk]`
- Test 5 câu hỏi mẫu

## Tiêu chí hoàn thành

- [x] Truy xuất đúng đoạn cho cả 5 câu hỏi mẫu
- [x] Không lẫn chunk của sách khác

## Ghi chú

- Thay đổi so với plan: full-text dùng cấu hình `simple`, chưa có cross-encoder, test dùng embedding giả theo từ; xem [ADR 0004](../decisions/0004-hybrid-retrieval.md).
- Kết thúc ngày 7 là hết khối RAG, viết tóm tắt ngắn vào `docs/` nếu có thay đổi so với plan.

---

[← Ngày 6](day-06.md) · [Mục lục](README.md) · [Ngày 8 →](day-08.md)
