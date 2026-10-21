# Migrations

File SQL đánh số, chạy theo thứ tự tên file, mỗi file một transaction. File đã chạy được ghi
vào `app_private.schema_migrations` nên chạy lại lệnh migrate không làm gì thêm. Không sửa file
đã merge, thêm file mới.

Chạy (từ thư mục gốc repo, dùng `DATABASE_URL` trong `.env`):

```bash
uv run python -m book_review_api.migrate
```

Lệnh này chạy các file ở đây rồi tạo bảng checkpoint/store của LangGraph trong schema
`langgraph`. Xem thêm README gốc.

| File | Nội dung |
| --- | --- |
| `0001_supabase_compat.sql` | Role `anon`/`authenticated`, `auth.users`, `auth.uid()` khi chạy trên Postgres thuần |
| `0002_app_tables.sql` | `projects`, `assets`, `documents`, `chunks` + RLS `user_id = auth.uid()` |
| `0003_langgraph_schema.sql` | Schema `langgraph` cho checkpointer và store |
| `0004_vector_store.sql` | pgvector: `langchain_pg_embedding` + HNSW, RLS theo `user_id`, `app_private.upsertion_record` cho Indexing API |
