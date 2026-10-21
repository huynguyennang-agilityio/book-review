-- Kho vector cho RAG (ngày 6): bảng của `langchain-postgres` PGVector, index HNSW, RLS.
-- PGVector dùng bảng `langchain_pg_collection` / `langchain_pg_embedding` với tên và cột cố định,
-- nên tạo sẵn ở đây (cùng schema với bản của thư viện) để có cột sinh, index và RLS.
-- Số chiều 768 phải khớp `embedding_dim` trong config (test kiểm tra).
-- `public.documents` / `public.chunks` của ngày 4 chưa dùng cho vector; citation ở ngày 8 trỏ
-- tới `langchain_pg_embedding.id`.

create extension if not exists vector;

create table public.langchain_pg_collection (
  uuid uuid primary key default gen_random_uuid(),
  name varchar not null unique,
  cmetadata json
);

create table public.langchain_pg_embedding (
  id varchar primary key,
  collection_id uuid references public.langchain_pg_collection (uuid) on delete cascade,
  embedding vector(768),
  document varchar,
  cmetadata jsonb,
  -- Chủ sở hữu và sách lấy từ metadata PGVector ghi. `user_id` rỗng nghĩa là chunk công khai
  -- (trang web, dùng chung theo `book_id`); có `user_id` là tài liệu riêng của người đó.
  user_id uuid generated always as (nullif(cmetadata ->> 'user_id', '')::uuid) stored,
  book_id text generated always as (cmetadata ->> 'book_id') stored
);

create index ix_cmetadata_gin on public.langchain_pg_embedding using gin (cmetadata jsonb_path_ops);
create index langchain_pg_embedding_hnsw_idx
  on public.langchain_pg_embedding using hnsw (embedding vector_cosine_ops);
create index langchain_pg_embedding_user_idx on public.langchain_pg_embedding (user_id);
create index langchain_pg_embedding_book_idx on public.langchain_pg_embedding (book_id);

-- PGVector tự `get_or_create` collection; tạo sẵn để người dùng thường không phải insert.
insert into public.langchain_pg_collection (name) values ('book_chunks');

alter table public.langchain_pg_collection enable row level security;
alter table public.langchain_pg_embedding enable row level security;

create policy collection_select_all on public.langchain_pg_collection
  for select to authenticated using (true);

-- Đọc: chunk công khai và chunk của chính mình. Ghi: chỉ chunk của chính mình. Chunk công khai
-- do tiến trình nạp có quyền chủ bảng (bỏ qua RLS) ghi, không phải role của người dùng.
create policy embedding_select on public.langchain_pg_embedding
  for select to authenticated using (user_id is null or user_id = (select auth.uid()));
create policy embedding_insert_own on public.langchain_pg_embedding
  for insert to authenticated with check (user_id = (select auth.uid()));
create policy embedding_update_own on public.langchain_pg_embedding
  for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy embedding_delete_own on public.langchain_pg_embedding
  for delete to authenticated using (user_id = (select auth.uid()));

revoke all on public.langchain_pg_collection, public.langchain_pg_embedding from anon;
grant select on public.langchain_pg_collection to authenticated;
grant select, insert, update, delete on public.langchain_pg_embedding to authenticated;

-- Sổ ghi nhận cho Indexing API (`SQLRecordManager`): key băm của chunk theo namespace. Chỉ chứa
-- hash, không có nội dung; nằm ngoài schema `public` nên không lộ qua API của Supabase.
create table app_private.upsertion_record (
  uuid varchar primary key,
  key varchar,
  namespace varchar not null,
  group_id varchar,
  updated_at double precision,
  constraint uix_key_namespace unique (key, namespace)
);
create index ix_upsertion_record_key on app_private.upsertion_record (key);
create index ix_upsertion_record_namespace on app_private.upsertion_record (namespace);
create index ix_upsertion_record_group_id on app_private.upsertion_record (group_id);
create index ix_upsertion_record_updated_at on app_private.upsertion_record (updated_at);
create index ix_key_namespace on app_private.upsertion_record (key, namespace);
