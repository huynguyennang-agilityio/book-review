# CLAUDE.md

Hướng dẫn cho Claude khi làm việc trong repo này. Người dùng nói tiếng Việt; trả lời tiếng Việt, ngắn gọn.

## Cấu trúc repo

- `apps/api` (`book_review_api`): FastAPI, agents, RAG, storyboard, providers (Gemini, Tavily).
- `apps/worker` (`book_review_worker`): worker hàng đợi.
- `apps/web`: web Next.js (pnpm).
- `scripts/`: `run_research.py`, `run_storyboard.py`, `build_rag_fixtures.py`, `measure_embeddings.py`.
- `evals/golden/<slug>/`: 10 sách golden và nguồn của chúng. `db/migrations/`: SQL. `tests/`, `docs/`, `spikes/` (không lint).

## Chỗ chạy script thật

Script gọi Gemini/Tavily cần key. Cloud sandbox không có key và bị chặn host Gemini, nên chạy trên máy Mac của người dùng (Remote Control):

- Repo: `/Users/nanghuy/Desktop/Projects/Review book/resource/book-review`
- Key nằm trong `.env` ở thư mục đó (đã gitignore). Chỉ đọc tên biến; không in, không log, không commit giá trị.
- Cấu hình hiện tại: `GEMINI_MODEL=gemini-3.5-flash-lite`, `SEARCH_PROVIDER=tavily` (cần `GOOGLE_API_KEY`, `TAVILY_API_KEY`).
- Giám khảo faithfulness mặc định `gemini-3.1-flash-lite`. Gói free của `gemini-3.5-flash` chỉ 20 request/ngày, không đủ chạy eval.

## Lệnh chuẩn

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/run_research.py "Đắc nhân tâm"
uv run python scripts/run_storyboard.py nha-gia-kim sapiens   # slug trong evals/golden
uv run --group eval python evals/run_ragas.py                # eval faithfulness, báo cáo ở docs/evals/
docker compose up -d                                          # Postgres + pgvector, Redis
uv run python -m book_review_api.migrate                      # chạy lại được
```

Postgres mặc định cổng 5432 (`docker-compose.yml`, `.env`). Test RLS/integration cần `TEST_DATABASE_URL`.

## Quy trình làm việc

Người dùng chỉ cần kết quả cuối cùng.

1. Tự chạy test và script cần thiết, không nhờ người dùng chạy tay.
2. Lỗi sửa được (code, test, lint, mypy, CI) thì tự sửa và chạy lại.
3. Làm trên nhánh riêng, mở PR, đợi CI xanh rồi merge (người dùng đã đồng ý). Không push thẳng `main`.
4. Chỉ dừng lại báo người dùng khi lỗi do quota, rate limit, giới hạn key, key thiếu/hết hạn, hoặc việc cần họ quyết định.
5. Báo cáo cuối chỉ nêu kết quả: đã làm gì, PR nào đã merge, script cho ra gì, chi phí nếu có.
