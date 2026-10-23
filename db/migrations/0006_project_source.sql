-- Nguồn của project: "book" (research từ tên sách) hoặc "user_review" (bài review người dùng dán,
-- tab "Từ bài review có sẵn"). Project cũ là "book".
alter table public.projects
  add column source text not null default 'book' check (source in ('book', 'user_review'));
