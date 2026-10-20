# Ngày 2: Spike stack

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Chứng minh toàn bộ đường đi kỹ thuật chạy được end-to-end ở mức "hello": graph LangGraph có checkpoint và interrupt, đi qua AG-UI lên CopilotKit, rồi quay lại, có trace trên LangSmith.

## Phụ thuộc / chuẩn bị

- Docker
- Tài khoản LangSmith, Gemini API key
- Kết quả ngày 1

## Công việc

### Hạ tầng local

- [x] Viết `docker-compose.yml` với Postgres có `pgvector` và Redis.
- [x] Kiểm tra `CREATE EXTENSION vector;` chạy được.

### LangGraph

- [x] Graph 2 node: `hello` → `ask_user` (gọi `interrupt()`), dùng `PostgresSaver` (`langgraph-checkpoint-postgres`).
- [x] Tắt process giữa chừng, chạy lại với cùng `thread_id`, xác nhận graph tiếp tục từ interrupt.

### AG-UI + CopilotKit

- [x] FastAPI expose endpoint `/agent` bằng adapter LangGraph ↔ AG-UI.
- [x] Trang Next.js tối thiểu dùng CopilotKit, hiển thị interrupt bằng `renderAndWaitForResponse` (thực tế dùng `useInterrupt` của CopilotKit v2, xem docs/spikes/day-02-stack.md), gửi câu trả lời về graph.

### Observability

- [x] Bật `LANGSMITH_TRACING=true`, kiểm tra trace có đủ 2 node và gom theo `thread_id`.

## Đầu ra

- `docker-compose.yml` dùng được
- `spikes/stack/` chứa graph, API và trang web hello
- `docs/spikes/day-02-stack.md`: version thư viện đã pin, các lỗi gặp phải

## Tiêu chí hoàn thành

- [x] Một interrupt đi từ graph lên UI và quay lại thành công
- [x] Resume sau khi restart server
- [x] Có trace trên LangSmith

## Ghi chú

- Pin version LangChain, LangGraph, CopilotKit, AG-UI ngay hôm nay vì API thay đổi nhanh.
- Bọc adapter AG-UI trong một module riêng để dễ thay sau này.

---

[← Ngày 1](day-01.md) · [Mục lục](README.md) · [Ngày 3 →](day-03.md)
