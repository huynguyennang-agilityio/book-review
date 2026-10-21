-- Những thứ Supabase đã có sẵn: role `anon`/`authenticated`, schema `auth`, bảng `auth.users`,
-- hàm `auth.uid()`. Trên Postgres thuần (docker compose, CI) thì tạo bản tối thiểu để RLS
-- chạy giống Supabase. Trên Supabase khối này không đụng vào gì.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;

  if not exists (select 1 from pg_namespace where nspname = 'auth') then
    create schema auth;
    grant usage on schema auth to anon, authenticated;
  end if;

  if to_regclass('auth.users') is null then
    create table auth.users (
      id uuid primary key,
      email text
    );
  end if;

  if to_regprocedure('auth.uid()') is null then
    -- Giống hàm của Supabase: đọc `sub` từ claims mà backend set theo từng request.
    create function auth.uid() returns uuid
      language sql stable
      as $f$
        select coalesce(
          nullif(current_setting('request.jwt.claim.sub', true), ''),
          nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
        )::uuid
      $f$;
    grant execute on function auth.uid() to anon, authenticated;
  end if;
end
$$;
