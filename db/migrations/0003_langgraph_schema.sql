-- Bảng checkpoint và store của LangGraph nằm trong schema riêng, không nằm trong `public`,
-- để Data API của Supabase (chỉ mở `public`) không lộ state của graph. Bảng do
-- `PostgresSaver.setup()` / `PostgresStore.setup()` tạo, chạy cùng lệnh migrate.
create schema if not exists langgraph;
revoke all on schema langgraph from public;
