-- Bảng ứng dụng. Mọi bảng có `user_id` và RLS `user_id = auth.uid()`.
-- Backend truy vấn bằng role `authenticated` + claims của người dùng (xem `db.py`),
-- không dùng service_role cho dữ liệu người dùng.

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  book_title text not null check (char_length(book_title) between 1 and 200),
  thread_id text not null unique,
  status text not null default 'created' check (
    status in ('created', 'running', 'awaiting_review', 'done', 'failed', 'cancelled', 'rejected')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Cho khoá ngoại (project_id, user_id) ở các bảng con: không gắn được asset vào project người khác.
  unique (id, user_id)
);
create index projects_user_created_idx on public.projects (user_id, created_at desc);

create table public.assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  project_id uuid not null,
  kind text not null check (kind in ('image', 'audio', 'video', 'subtitle', 'caption', 'other')),
  -- Chỉ lưu đường dẫn trong object storage, không lưu binary.
  storage_path text not null,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (project_id, user_id) references public.projects (id, user_id) on delete cascade
);
create index assets_project_idx on public.assets (project_id);

-- Tài liệu riêng của người dùng cho RAG. `project_id` để trống nghĩa là dùng chung cho mọi project
-- của người đó.
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  project_id uuid,
  source_url text,
  title text,
  content_hash text not null,
  created_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (project_id, user_id) references public.projects (id, user_id) on delete cascade
);
create index documents_user_hash_idx on public.documents (user_id, content_hash);

-- Cột embedding (pgvector) và index thêm ở ngày 6.
create table public.chunks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  document_id uuid not null,
  chunk_index integer not null check (chunk_index >= 0),
  content text not null,
  token_count integer,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index),
  foreign key (document_id, user_id) references public.documents (id, user_id) on delete cascade
);

create function app_private.touch_updated_at() returns trigger
  language plpgsql
  as $$
  begin
    new.updated_at := now();
    return new;
  end
  $$;

create trigger projects_touch_updated_at
  before update on public.projects
  for each row execute function app_private.touch_updated_at();

do $$
declare
  t text;
begin
  foreach t in array array['projects', 'assets', 'documents', 'chunks'] loop
    execute format('alter table public.%I enable row level security', t);
    -- `(select auth.uid())` để Postgres tính một lần mỗi câu lệnh thay vì mỗi dòng.
    execute format(
      'create policy %I on public.%I for select to authenticated using (user_id = (select auth.uid()))',
      t || '_select_own', t);
    execute format(
      'create policy %I on public.%I for insert to authenticated with check (user_id = (select auth.uid()))',
      t || '_insert_own', t);
    execute format(
      'create policy %I on public.%I for update to authenticated '
      'using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()))',
      t || '_update_own', t);
    execute format(
      'create policy %I on public.%I for delete to authenticated using (user_id = (select auth.uid()))',
      t || '_delete_own', t);
    -- Supabase mặc định grant bảng public cho `anon`; app không cho truy cập ẩn danh.
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end
$$;
