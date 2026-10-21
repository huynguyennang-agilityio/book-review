# ADR 0004: Hybrid retrieval bằng pgvector + full-text `simple`, gộp RRF, rerank cắm được

- Trạng thái: Chấp nhận
- Ngày: 2026-10-21
- Liên quan: [Ngày 7](../plan/day-07.md), migration `0005_chunk_fulltext.sql`, `rag/retrieve.py`

## Quyết định

- `retrieve(book_id, query)` lấy ứng viên từ hai nhánh trên cùng bảng `langchain_pg_embedding`: vector cosine (HNSW) và full-text (cột `fts` + GIN), mỗi nhánh 24 ứng viên, gộp bằng RRF (k=60), giữ top 8, rồi rerank xuống 4. Số 8 và 4 đặt trong config (`retrieve_top_k`, `rerank_top_n`).
- Full-text dùng cấu hình `simple`: Postgres không có cấu hình tiếng Việt, mỗi âm tiết là một token, giữ nguyên dấu nên tên riêng khớp chính xác. Truy vấn là OR của các từ trong câu hỏi, xếp hạng bằng `ts_rank_cd`.
- Rerank là `Reranker` (Protocol). Mặc định `rerank_provider=none` (giữ thứ tự RRF); `llm` dùng Gemini chấm lại và tự rơi về thứ tự RRF nếu LLM lỗi hoặc trả đầu ra sai. Chưa làm cross-encoder: cắm thêm bằng một class `Reranker` khác.
- Luôn lọc `book_id` trong SQL. Truy vấn chạy trên engine của người dùng (`make_vector_engine(url, user_id)`) nên RLS vẫn quyết định chunk riêng của ai được thấy.

## Giới hạn đã biết

- Tìm không dấu ("Dac nhan tam") không khớp nhánh full-text vì chưa bỏ dấu; `unaccent` không immutable nên cần hàm bọc nếu sau này cần.
- Test dùng embedding giả theo từ (không gọi API), nên chứng minh đường đi hybrid và lọc sách, chưa đo chất lượng với Gemini embedding thật. Chất lượng thật sẽ đo bằng golden set ở các ngày eval.
- HNSW lọc theo `book_id` sau khi duyệt index có thể trả ít hơn số yêu cầu khi sách nhỏ so với toàn kho; hiện kho còn nhỏ và có btree `book_id` nên planner chọn được đường chính xác. Xem lại (pgvector iterative scan) khi kho lớn.
