# apps/web

Next.js (App Router, TypeScript) + CopilotKit v2. Version pin theo spike ngày 2 ([docs/spikes/day-02-stack.md](../../docs/spikes/day-02-stack.md)).

```bash
pnpm install            # ở gốc repo
pnpm --filter @book-review/web dev
```

- `app/api/copilotkit/[[...slug]]/route.ts`: CopilotRuntime trỏ tới `AGENT_URL` (mặc định `http://localhost:8000/agent`). Agent tên `review`.
- `app/page.tsx`: `CopilotChat`, chưa có agent thật cho tới ngày 4.
- Khi nâng CopilotKit phải nâng `@ag-ui/client` cho khớp (lỗi 2 trong spike ngày 2).
