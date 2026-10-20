# Ngày 9: Research agent: create_agent, middleware, xác nhận sách

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Agent tự tìm và nạp đủ nguồn, dừng khi đủ thông tin, có giới hạn chi phí và từ chối thể loại bị loại trừ.

## Phụ thuộc / chuẩn bị

- Ngày 8

## Công việc

### Agent (`agents/research.py`)

- [ ] `create_agent` với Gemini Flash, system prompt trong `prompts/research_v1.md`, structured output `ResearchResult`.

### Middleware (`agents/middleware.py`)

- [ ] `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware`, `PIIMiddleware`, `SummarizationMiddleware`.
- [ ] Tự viết `CostTrackingMiddleware`: cộng token và chi phí vào state, dừng khi vượt ngân sách.
- [ ] Tự viết `GenreGuardMiddleware`: dừng ngay khi phát hiện thể loại bị loại trừ.

### Graph

- [ ] Node `research_agent` gọi agent, ghi kết quả vào state.
- [ ] Node `identify_confirm`: nếu trùng tên hoặc `low_confidence` thì `interrupt()` cho người dùng chọn đúng cuốn.

### Kiểm tra

- [ ] Chạy thật với 3 sách (1 fiction VN, 1 non-fiction, 1 trùng tên) và 1 truyện tiên hiệp.

## Đầu ra

- Research agent chạy trong graph
- Trace LangSmith của 4 lần chạy thử

## Tiêu chí hoàn thành

- [ ] Agent nạp ≥ N nguồn cho 3 sách
- [ ] Từ chối đúng truyện tiên hiệp với mã `GENRE_EXCLUDED`

## Ghi chú

- Đặt N mặc định = 4 trong config, chỉnh sau.

---

[← Ngày 8](day-08.md) · [Mục lục](README.md) · [Ngày 10 →](day-10.md)
