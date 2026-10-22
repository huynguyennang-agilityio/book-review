# Book Review AI

Web app nhập tên sách, AI research (RAG) và viết kịch bản có trích dẫn nguồn, người dùng duyệt trên giao diện, rồi nhận video review dọc 9:16 (720×1280) để đăng TikTok, YouTube Shorts và Reels.

- Kế hoạch tổng: [docs/project-plan-v5.md](docs/project-plan-v5.md)
- Kế hoạch theo ngày: [docs/plan/](docs/plan/README.md)

## Cấu trúc

```text
apps/
  api/      FastAPI + LangGraph (uv workspace)
  worker/   arq render worker: TTS, ảnh, motion, compose (uv workspace)
  web/      Next.js + CopilotKit (pnpm)
evals/      dataset golden + RAGAS
db/         migrations, RLS
tests/      unit, integration, rls, timeline
infra/      Dockerfiles
spikes/     code thử nghiệm ngày 1–2
docs/       plan, quyết định kỹ thuật
```

## Chạy local

```bash
cp .env.example .env
docker compose up -d          # Postgres + pgvector, Redis
uv sync                       # Python workspace
uv run python -m book_review_api.migrate   # tạo bảng, RLS, bảng LangGraph (chạy lại được)
uv run pytest
uv run uvicorn book_review_api.main:app --reload

pnpm install                  # web
pnpm web:dev                  # http://localhost:3000
```

Ảnh video có hai cách (chọn sau khi duyệt kịch bản): **auto** (Fal tạo ảnh, cần `FAL_KEY`) hoặc **manual** (người dùng tải 1 ảnh cho mỗi prompt, không tốn tiền ảnh). Thử manual không qua web, dùng ảnh mẫu rồi dựng video:

```bash
uv run python scripts/run_scene_images.py --manual-dir var/manual-samples --make-samples nha-gia-kim
uv run python scripts/run_media.py var/media/images/storyboard_nha-gia-kim.json
```

Kiểm tra trước khi push (CI chạy y hệt):

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
pnpm web:lint && pnpm web:typecheck && pnpm web:build
```

## CI và Docker

- `ci.yml`: ruff, mypy, pytest (Postgres + pgvector), eslint/typecheck/build web, build 3 image Docker.
- `evals.yml`: khi PR đổi prompt, RAG, storyboard hoặc config, chạy eval 5 sách và chặn merge nếu faithfulness < 0.9. Cần secret `GOOGLE_API_KEY` trong GitHub Environment `eval`.
- Deploy: xem mục "Deploy và release" bên dưới.
- Image: `infra/docker/{api,worker,web}.Dockerfile`, xem [infra/docker/README.md](infra/docker/README.md).

## Chạy toàn bộ bằng Docker (local)

```bash
docker compose up -d --build   # postgres, redis, api (tự migrate), worker, web
# mở http://localhost:3000 (đăng nhập Supabase), API http://localhost:8000/health
docker compose down            # dừng (giữ dữ liệu); thêm -v để xoá DB
```

`.env` cần khoá Gemini/Tavily, `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`; nếu cổng 5432 bận thì đặt `POSTGRES_PORT=5433`. Video ra ở `var/media/render/<id>/final_review.mp4`. Chạy thử không cần web/đăng nhập: `uv run python scripts/run_agent.py "Nhà giả kim" --api http://localhost:8001 --approve` (xem docstring).

## Deploy và release

- **Kiến trúc chạy thật:** Supabase (Postgres + pgvector, Auth) · VPS chạy `infra/deploy/docker-compose.yml` (API + worker + Redis, chung volume media) · web trên Vercel.
- `deploy.yml`: merge vào `main` → build image `api`/`worker` đẩy lên GHCR → smoke test (`scripts/smoke_test.py`: 1 video ngắn, ảnh placeholder, TTS thật) → deploy **staging**. Push tag `vX.Y.Z` → deploy **production** (Environment `production`, nên bật required reviewers).
- Mỗi Environment (`staging`, `production`) cần secret `SSH_HOST`, `SSH_USER`, `SSH_KEY`, biến `API_URL` (và tuỳ chọn `DEPLOY_PATH`). Thiếu `SSH_HOST` thì bước deploy được bỏ qua.
- Trên VPS: cài Docker, đặt `.env` (xem `.env.example`: `DATABASE_URL`, `SUPABASE_URL`, `GOOGLE_API_KEY`, `TAVILY_API_KEY`...) cạnh `docker-compose.yml`, `docker login ghcr.io` nếu package private. `deploy.sh` chạy migration rồi `docker compose up -d`.
- Web: kết nối repo với Vercel (root `apps/web`), đặt `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `API_URL` trỏ tới API của từng môi trường.
- Phát hành: `git tag v0.1.0 && git push origin v0.1.0`.

## Database và migration

Migration là file SQL trong [`db/migrations/`](db/migrations/README.md), chạy theo thứ tự tên file. Lệnh

```bash
uv run python -m book_review_api.migrate                       # dùng DATABASE_URL trong .env
uv run python -m book_review_api.migrate --database-url URL    # DB khác
```

chạy các file chưa chạy (ghi lại trong `app_private.schema_migrations`), rồi tạo bảng checkpoint và store của LangGraph trong schema `langgraph`. Chạy được từ DB trống và chạy lại nhiều lần không sao.

- Trên **Supabase**: `DATABASE_URL` là chuỗi kết nối trực tiếp hoặc session pooler (cổng 5432) của user `postgres`. Không dùng transaction pooler (6543) vì graph pool cần `search_path` lúc kết nối.
- Trên **Postgres thuần** (docker compose, CI): migration `0001` tự tạo role `anon`/`authenticated`, `auth.users` và `auth.uid()` giống Supabase để RLS chạy như nhau.

Dữ liệu người dùng (`projects`, `assets`, `documents`, `chunks`) đều có `user_id` và RLS `user_id = auth.uid()`. Backend không dùng `service_role`: mỗi request mở transaction với role `authenticated` và claims JWT của người gửi (`db.user_transaction`), nên Postgres tự lọc dữ liệu theo người dùng.

Test RLS và integration cần `TEST_DATABASE_URL` (xem `.env.example`; nếu cổng 5432 đã bị Postgres khác chiếm, chạy `POSTGRES_PORT=5433 docker compose up -d` và đổi cổng trong URL); thiếu thì các test này bị skip, CI thì bắt buộc có.

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run pytest
```

API: `GET /health` (không cần đăng nhập), `GET /me` (cần header `Authorization: Bearer <access_token Supabase>`), `POST /projects` (`{"book_title": "..."}`, tạo project và `thread_id` cho graph), `GET /projects/{id}`. Lỗi luôn trả `{code, message_vi, retryable}`, danh sách mã ở `apps/api/src/book_review_api/errors.py`.
