# Spike Ngày 2: stack

> Kết quả thử nghiệm cho [Ngày 2](../plan/day-02.md). Code thử nằm ở `spikes/stack/`.

## Trạng thái

| Hạng mục | Trạng thái | Ghi chú |
| --- | --- | --- |
| `docker-compose.yml` Postgres pgvector + Redis | ✅ Đã chạy | `CREATE EXTENSION vector` OK, pgvector 0.8.7; Redis trả PONG |
| Graph `hello → ask_user` với `interrupt()` + `PostgresSaver` | ✅ Đã chạy | |
| Resume sau khi tắt process (CLI) | ✅ Đã chạy | `resume_cli.py start` rồi `resume` ở process mới, cùng `thread_id` |
| Resume sau khi restart API (HTTP và UI) | ✅ Đã chạy | Tắt uvicorn lúc đang chờ interrupt, bật lại, gửi câu trả lời, graph chạy tiếp |
| FastAPI `/agent` qua AG-UI | ✅ Đã chạy | `ag-ui-langgraph`, bọc trong `api/agui_adapter.py` |
| Next.js + CopilotKit hiện interrupt và gửi câu trả lời | ✅ Đã chạy | Kiểm bằng Playwright (`web/e2e.mjs`), có cả biến thể restart API giữa chừng |
| Trace LangSmith đủ 2 node, gom theo `thread_id` | ✅ Đã chạy | Key thật trên máy local, project `review-book`. `check_trace.py day2-trace-1` ra 15 run: `LangGraph`, `hello`, `ChatGoogleGenerativeAI`, `ask_user`. Filter `metadata_key`/`metadata_value` theo `thread_id` dùng được, không phải sửa |
| Gọi Gemini thật trong node `hello` | ✅ Đã chạy | `gemini-3.5-flash`. CLI và E2E đều nhận câu chào do model sinh, run `ChatGoogleGenerativeAI` có trong trace. Xem lỗi 8, 9, 10 |

Chạy ngày 2026-10-20 trong container Linux (cloud), Python 3.12, Node 22. LangSmith và Gemini kiểm lại ngày 2026-10-21 trên macOS (máy local) với key thật, Node 20; E2E (`npm run e2e`, bản build `next start`) qua trong khoảng 12 giây.

## Version đã pin

Python (`spikes/stack/requirements.txt`):

| Gói | Version |
| --- | --- |
| langgraph | 1.2.16 |
| langgraph-checkpoint | 4.3.0 |
| langgraph-checkpoint-postgres | 3.2.0 |
| langchain-core | 1.6.12 |
| langchain-google-genai | 4.4.2 |
| langsmith | 0.14.11 |
| ag-ui-langgraph | 0.0.47 |
| ag-ui-protocol | 1.0.0 |
| fastapi | 0.154.0 |
| uvicorn | 0.54.0 |
| psycopg / psycopg-pool | 3.3.6 / 3.3.3 |

Node (`spikes/stack/web/package.json`, có `package-lock.json`):

| Gói | Version |
| --- | --- |
| @copilotkit/react-core, react-ui, runtime | 1.79.1 |
| @ag-ui/client | 1.0.2 (phải khớp bản CopilotKit dùng, xem lỗi 2) |
| next | 16.4.2 |
| react / react-dom | 19.3.1 |

Docker: `pgvector/pgvector:pg16`, `redis:7-alpine` (đã có từ scaffold).

## Lỗi gặp phải và cách xử lý

1. **`AsyncPostgresSaver` cần event loop đang chạy.** Tạo ở module level báo `RuntimeError: no running event loop`. Cách làm: mở `AsyncConnectionPool` (`autocommit=True`, `prepare_threshold=0`) và tạo saver trong `lifespan` của FastAPI, gắn route `/agent` luôn ở đó. Ngày 4 làm graph thật cũng cần theo cách này.
2. **Trùng `@ag-ui/client`.** Cài `@ag-ui/client@1.0.3` trong khi CopilotKit 1.79.1 kéo 1.0.2, TypeScript báo `HttpAgent` không gán được cho `AbstractAgent` (private `_debug` khác khai báo). Pin đúng 1.0.2. Khi nâng CopilotKit phải nâng `@ag-ui/client` theo.
3. **CopilotKit v1 đã deprecated từ 1.68.2.** `useLangGraphInterrupt` và `renderAndWaitForResponse` (kế hoạch ghi dùng cái này) nằm trong API v1. Spike dùng v2: `@copilotkit/react-core/v2` (`CopilotKit`, `CopilotChat`, `useInterrupt`) và `@copilotkit/runtime/v2` (`CopilotRuntime`, `createCopilotRuntimeHandler`). `renderAndWaitForResponse` của v1 dành cho tool gọi từ LLM (human-in-the-loop), không phải `interrupt()` của LangGraph; `useInterrupt` mới là cái khớp.
4. **Resume qua `forwardedProps.command.resume` đã deprecated.** Mặc định adapter phát interrupt kiểu cũ (custom event `on_interrupt`, `value` là chuỗi JSON) và log cảnh báo khi resume. Bật `emit_interrupt_outcome=True` trong `LangGraphAgent` thì run kết thúc bằng `RUN_FINISHED` có `outcome.type = "interrupt"`, client resume qua `RunAgentInput.resume[]`, và `useInterrupt` nhận `interrupt.message` sẵn. Vì vậy graph gọi `interrupt({"message": ...})`.
5. **Gõ chat trước khi `/api/copilotkit/info` trả về thì tin nhắn bị bỏ.** Chỉ gặp khi test tự động gõ ngay lúc trang vừa load. E2E chờ `networkidle`. Trang thật cần trạng thái "đang kết nối" trước khi cho gõ.
6. **CopilotKit runtime bật telemetry mặc định.** Tắt bằng `COPILOTKIT_TELEMETRY_DISABLED=true` (đã thêm vào `.env.example`).
7. **Docker Hub trả 429 trong container cloud.** Chỉ ảnh hưởng môi trường cloud; đã kéo ảnh qua `mirror.gcr.io` rồi tag lại. Máy local không cần.
8. **`gemini-2.5-flash` trả 404 với key mới** ("no longer available to new users"). Đổi mặc định sang `gemini-3.5-flash` (trong `graph.py` và `GEMINI_MODEL` ở `.env.example`). Lỗi gợi ý `gemini-3.8-flash`, nhưng free tier của 3.8 và 3.7 chỉ cho 20 request/ngày mỗi model, hết sau vài lần chạy; 3.5-flash và 3.1-flash-lite vẫn gọi được. Ngày 6 chọn model cho `llm_gemini.py` cần tính quota này.
9. **Gemini 3.x trả `content` dạng list block** (`[{"type": "text", "text": ..., "extras": {"signature": ...}}]`), `str(reply.content)` ra cả chữ ký. Dùng `reply.text`.
10. **Hết quota thì stream AG-UI treo, không báo lỗi.** `ChatGoogleGenerativeAI` tự retry 429 có backoff, UI đứng sau `on_chat_model_start`, E2E timeout ở chỗ chờ form. Đặt `max_retries=1, timeout=30` để lỗi nổi lên ngay. Graph thật cần bắt lỗi provider và báo cho người dùng.
11. **Trùng cổng trên máy local.** Máy đã có Postgres khác ở 5432 và một uvicorn khác ở 8000. Lúc kiểm chạy Postgres ở 5433 bằng file override ngoài repo (`ports: !override ["5433:5432"]`), `DATABASE_URL` trỏ 5433 trong `api/.env`, API ở 8001 và web chạy với `AGENT_URL=http://localhost:8001/agent`. Không đổi gì trong repo.
12. **`Client.list_runs()` của LangSmith báo deprecated** (gỡ sau 31/01/2027, thay bằng `client.runs.query()`). `check_trace.py` vẫn chạy, đổi khi làm observability thật.

## Việc còn lại

- Không còn việc nào của spike. Ghi chú cho các ngày sau: chọn model Gemini theo quota (lỗi 8), bắt lỗi provider trong graph (lỗi 10), chuyển `check_trace.py` sang `client.runs.query()` (lỗi 12).
