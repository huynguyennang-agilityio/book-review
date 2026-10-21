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
uv run pytest
uv run uvicorn book_review_api.main:app --reload

pnpm install                  # web
pnpm web:dev                  # http://localhost:3000
```

Kiểm tra trước khi push (CI chạy y hệt):

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
pnpm web:lint && pnpm web:typecheck && pnpm web:build
```

API: `GET /health` (không cần đăng nhập), `GET /me` (cần header `Authorization: Bearer <access_token Supabase>`). Lỗi luôn trả `{code, message_vi, retryable}`, danh sách mã ở `apps/api/src/book_review_api/errors.py`.
