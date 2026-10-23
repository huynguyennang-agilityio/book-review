# CLAUDE.md

Hướng dẫn cho Claude khi làm việc trong repo này. Người dùng nói tiếng Việt; trả lời tiếng Việt, ngắn gọn.

## Cấu trúc repo

- `apps/api` (`book_review_api`): FastAPI, agents, RAG, storyboard, providers (OpenAI viết kịch bản, Gemini, Tavily).
- `apps/worker` (`book_review_worker`): worker arq: job `tts` (edge-tts), `timeline`, stub `images`/`motion`/`compose`. Media ghi vào `MEDIA_DIR` (`var/media`).
- `apps/web`: web Next.js (pnpm).
- `scripts/`: `run_agent.py` (gọi `/agent` như web; `--review <file>` cho tab review có sẵn, `--mode manual` tự tải ảnh mẫu), `run_media.py`, `run_review_text.py` (chia bài review nguyên văn + metadata Gemini, `--out` ghi storyboard JSON), `run_characters.py`, `run_scene_images.py`, `run_research.py`, `run_storyboard.py`, `build_rag_fixtures.py`, `measure_embeddings.py`.
- `evals/golden/<slug>/`: 10 sách golden và nguồn của chúng. `evals/review-text/`: 3 bài review mẫu cho tab "Từ bài review có sẵn" ([docs/review-text.md](docs/review-text.md)). `db/migrations/`: SQL. `tests/`, `docs/`, `spikes/` (không lint).

## Chỗ chạy script thật

Script gọi Gemini/Tavily cần key. Cloud sandbox không có key và bị chặn host Gemini, nên chạy trên máy Mac của người dùng (Remote Control):

- Repo: `/Users/nanghuy/Desktop/Projects/Review book/resource/book-review`
- Key nằm trong `.env` ở thư mục đó (đã gitignore). Chỉ đọc tên biến; không in, không log, không commit giá trị.
- Cấu hình hiện tại: `GEMINI_MODEL=gemini-3.5-flash-lite`, `SEARCH_PROVIDER=tavily` (cần `GOOGLE_API_KEY`, `TAVILY_API_KEY`). Có `OPENAI_API_KEY` thì kịch bản do `gpt-5.4-mini` viết (`WRITER_PROVIDER=auto`); quá tải (503, 429, timeout) thì tự chuyển sang Gemini dự phòng.
- Giám khảo faithfulness mặc định `gemini-3.1-flash-lite`. Gói free của `gemini-3.5-flash` chỉ 20 request/ngày, không đủ chạy eval.

## Lệnh chuẩn

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/run_research.py "Đắc nhân tâm"
uv run python scripts/run_storyboard.py nha-gia-kim sapiens   # slug trong evals/golden
uv run python scripts/run_review_text.py evals/review-text/nha-gia-kim.md --out var/review-text
uv run --group eval python evals/run_ragas.py                # eval faithfulness, báo cáo ở docs/evals/
docker compose up -d                                          # Postgres + pgvector, Redis, worker
uv run arq book_review_worker.main.WorkerSettings             # worker chạy ngoài docker
uv run python scripts/run_media.py                            # TTS + timeline thật qua worker
uv run python -m book_review_api.migrate                      # chạy lại được
```

Postgres mặc định cổng 5432 (`docker-compose.yml`, `.env`). Test RLS/integration cần `TEST_DATABASE_URL`.

## Quy trình làm việc

Người dùng chỉ cần kết quả cuối cùng.

1. Tự chạy test và script cần thiết, không nhờ người dùng chạy tay.
2. Lỗi sửa được (code, test, lint, mypy, CI) thì tự sửa và chạy lại.
3. Làm trên nhánh riêng, mở PR, đợi CI xanh rồi tự merge (`gh pr merge --merge`). Người dùng đã cho phép rõ ràng việc tự merge trên máy Mac, không cần hỏi lại. Không push thẳng `main`.
4. Chỉ dừng lại báo người dùng khi lỗi do quota, rate limit, giới hạn key, key thiếu/hết hạn, hoặc việc cần họ quyết định.
5. Báo cáo cuối chỉ nêu kết quả: đã làm gì, PR nào đã merge, script cho ra gì, chi phí nếu có.

## Skills

`.claude/skills/`: `create-tasks` (chia plan artifact thành task), `doing-tasks` (làm hết list task, tự PR + merge, không chạy eval trừ khi được bảo, cuối cùng gom issue thành artifact).
