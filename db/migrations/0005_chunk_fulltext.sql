-- Full-text search cho hybrid retrieval (ngày 7): cột tsvector sinh từ nội dung chunk.
-- Dùng cấu hình `simple` (không stemming, không stop-word) vì Postgres không có cấu hình tiếng
-- Việt; mỗi âm tiết là một token, giữ nguyên dấu nên tên riêng như "Santiago" hay "Đắc Nhân Tâm"
-- khớp chính xác. RLS của bảng áp dụng như với truy vấn vector.

alter table public.langchain_pg_embedding
  add column fts tsvector
  generated always as (to_tsvector('simple', coalesce(document, ''))) stored;

create index langchain_pg_embedding_fts_idx
  on public.langchain_pg_embedding using gin (fts);
