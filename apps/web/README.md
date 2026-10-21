# apps/web

Next.js (App Router, TypeScript). Version pin theo spike ngày 2 ([docs/spikes/day-02-stack.md](../../docs/spikes/day-02-stack.md)).

```bash
pnpm install            # ở gốc repo
pnpm --filter @book-review/web dev
```

Cần `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` và `API_URL` (xem `.env.example`; đặt trong `apps/web/.env.local`).

## Luồng ngày 14

- `app/page.tsx`: chưa đăng nhập thì hiện `LoginForm` (Supabase Auth, email + mật khẩu); đã đăng nhập thì hiện màn chính.
- `app/_lib/run.ts`: `useReviewRun` tạo project (`POST /projects`), rồi chạy graph qua `HttpAgent` của `@ag-ui/client` tới `/agent`, kèm JWT. Đọc event: `node` (tiến độ node, do graph phát), `source` (nguồn tìm thấy, đã đọc, đã nạp), `RUN_FINISHED` với `outcome=interrupt` (`identify_confirm`, `review_script`). Chọn sách xong thì gửi `resume` ở lần chạy tiếp theo.
- `app/api/backend/[...path]/route.ts`: proxy REST và SSE tới FastAPI (`API_URL`), giữ header `Authorization`. Trình duyệt không gọi thẳng API nên không cần CORS.
- `app/api/copilotkit/`: CopilotRuntime của spike ngày 2, màn chính không dùng nữa. Khi nâng CopilotKit phải nâng `@ag-ui/client` cho khớp (lỗi 2 trong spike).
- Thử không cần tài khoản Supabase: `uv run python scripts/run_agent.py x --print-token` ký JWT thử cho Postgres local (xem docstring script), rồi đặt session vào localStorage.

## Ngày 15: duyệt kịch bản, huỷ

- `app/_components/ScriptReview.tsx` hiện khi interrupt `review_script`: điểm bám nguồn, cờ `LOW_FAITHFULNESS`, chi phí ước tính, sửa trực tiếp từng cảnh, viết lại một cảnh bằng lời (`POST /projects/{id}/scenes/{id}/rewrite`), nút Duyệt gửi `resume {approved, edits}`.
- `app/_lib/script.ts`: parse payload và tô câu chưa có căn cứ (hàm thuần).
- Nút Huỷ gọi `POST /projects/{id}/cancel`; lỗi hiển thị theo mã (`ERROR_TEXT` trong `app/_lib/run.ts`).
