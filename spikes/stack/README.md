# Spike stack (Ngày 2)

Code thử nghiệm, không dùng trong sản phẩm. Kết quả và version đã pin nằm ở [docs/spikes/day-02-stack.md](../../docs/spikes/day-02-stack.md).

Luồng: trang Next.js (CopilotKit v2) → `/api/copilotkit` (CopilotRuntime) → FastAPI `/agent` (AG-UI) → graph LangGraph `hello → ask_user` có `interrupt()`, checkpoint trên Postgres.

## Chuẩn bị

- Docker Desktop đang chạy
- Python 3.12, `uv` (hoặc `pip`), Node 22
- File `.env` ở gốc repo (copy từ `.env.example`), điền `GOOGLE_API_KEY` và `LANGSMITH_API_KEY`. Không có `GOOGLE_API_KEY` thì node `hello` trả câu chào cố định, vẫn chạy được.

## Chạy

```bash
# 1. Postgres (pgvector) + Redis, ở gốc repo
docker compose up -d
docker compose exec postgres psql -U postgres -d book_review -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 2. API, cổng 8000
cd spikes/stack
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
cd api && cp ../../../.env .env    # hoặc export biến môi trường
../.venv/bin/uvicorn main:app --port 8000

# 3. Web, cổng 3000 (terminal khác)
cd spikes/stack/web
npm install
npm run dev
```

Mở http://localhost:3000, gõ một câu bất kỳ vào chat. Graph chào, rồi hiện form hỏi tên sách (interrupt). Gõ tên sách và bấm Gửi, graph chạy tiếp và trả lời "Đã nhận: «…»".

## Kiểm tra

| Việc | Lệnh |
| --- | --- |
| Resume sau khi tắt process (không qua HTTP) | `cd api && ../.venv/bin/python resume_cli.py start t1`, rồi `../.venv/bin/python resume_cli.py resume t1 "Nhà giả kim"` |
| Resume sau khi restart API (qua UI) | Lúc form đang hiện, Ctrl+C uvicorn, chạy lại, rồi bấm Gửi |
| E2E tự động bằng trình duyệt | `cd web && npx playwright install chromium && npm run e2e` |
| Trace LangSmith đủ 2 node | `cd api && ../.venv/bin/python check_trace.py <thread_id>` (thread_id xem trong trace hoặc log) |

## File

- `api/graph.py`: graph 2 node, `ask_user` gọi `interrupt({"message": ...})`
- `api/agui_adapter.py`: chỗ duy nhất import `ag_ui_langgraph`, để sau dễ thay
- `api/main.py`: FastAPI, pool Postgres, gắn `/agent` trong lifespan
- `api/resume_cli.py`: thử resume bằng `PostgresSaver` đồng bộ
- `api/check_trace.py`: đếm run trên LangSmith theo `thread_id`
- `web/app/api/copilotkit/[[...slug]]/route.ts`: CopilotRuntime v2 trỏ tới `AGENT_URL` (mặc định `http://localhost:8000/agent`)
- `web/app/page.tsx`: `CopilotChat` + `useInterrupt` hiện form hỏi tên sách
- `web/e2e.mjs`: script Playwright chạy cả vòng, có tuỳ chọn `--restart "<lệnh>"`
