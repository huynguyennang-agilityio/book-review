# Ngày 1: Provider OpenAI và bảng giá theo model

> Tính năng viết kịch bản bằng OpenAI · Nguồn: [plan OpenAI + dự phòng](README.md)

## Mục tiêu

Tạo được chat model OpenAI cho phần viết kịch bản, structured output chạy đúng schema hiện có, chi phí tính đúng giá.

## Phụ thuộc / chuẩn bị

- `OPENAI_API_KEY` trong `.env`
- Ngày 10 (storyboard có citation), ngày 11 (`estimate_cost`)

## Công việc

- [x] **Thư viện**: thêm `langchain-openai` vào `apps/api`.
- [x] **Config**: `openai_api_key`, `writer_provider` (`openai` | `gemini`, mặc định `openai` nếu có key), `writer_model=gpt-5.4-mini`.
- [x] **Provider**: `providers/llm_openai.py` với `make_writer_model(settings)`; nhiệt độ thấp, timeout rõ ràng; dùng chung `llm_rpm` nếu đặt.
- [x] **Structured output**: kiểm tra `Outline`, `SectionDraft`, các schema rewrite qua `with_structured_output` của OpenAI (strict JSON schema: trường tuỳ chọn, `Literal`, giới hạn độ dài). Sửa schema nếu OpenAI từ chối, không đổi dữ liệu ra.
- [x] **Giá theo model**: bảng `model -> (giá input, giá output)` trong config; `Usage` ghi token theo model đã trả lời; `cost.usd` của storyboard cộng theo từng model.
- [x] **Test**: model giả trả đúng schema; tính tiền 2 model khác giá; không có key thì `writer_provider` rơi về Gemini.
- [ ] **Chạy thật**: `run_storyboard.py nha-gia-kim` bằng OpenAI, so số cảnh, số từ, chi phí với Gemini.

> Đã nối luôn `make_writer_model` vào `graph/live.py` (storyboard, viết lại cảnh, sửa cảnh của faithfulness) và các script; không có `OPENAI_API_KEY` thì vẫn chạy Gemini như cũ. Còn chạy thật khi có key.

## Tiêu chí hoàn thành

- [ ] Viết được storyboard 1 sách golden bằng `gpt-5.4-mini`, citation hợp lệ, chi phí đúng giá OpenAI

---

[Mục lục](README.md) · [Ngày 2 →](day-02.md)
