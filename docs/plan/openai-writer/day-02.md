# Ngày 2: Dự phòng khi quá tải

> Tính năng viết kịch bản bằng OpenAI · Nguồn: [plan OpenAI + dự phòng](README.md)

## Mục tiêu

Model nào bị quá tải thì lời gọi đó tự chuyển sang model dự phòng, run không dừng.

## Phụ thuộc / chuẩn bị

- Ngày 1 của bộ này

## Công việc

- [x] **Phân loại lỗi**: hàm `is_overloaded(exc)` nhận 503, 429, 500/502/504, timeout của cả Google (`ServerError`, `GoogleAPIError`) và OpenAI (`RateLimitError`, `InternalServerError`, `APITimeoutError`). Lỗi khác không chuyển model.
- [x] **Dự phòng**: `call_structured` nhận danh sách model theo thứ tự; lỗi quá tải ở model chính thì gọi ngay model dự phòng; cả hai lỗi thì mới chờ 15s/30s/60s rồi thử lại từ đầu.
- [x] **Cấu hình**: `writer_fallback_model=gemini-3.5-flash-lite`, `judge_fallback_model=gemini-3.5-flash-lite`, `gemini_fallback_model=gemini-3.1-flash-lite` cho research, rerank, prompt ảnh. Research agent (tool calling) dùng `with_fallbacks` của LangChain với cùng `is_overloaded`.
- [ ] **Ghi nhận**: log mỗi lần chuyển model (model cũ, model mới, mã lỗi); metadata run và LangSmith ghi model thực sự đã viết; cảnh báo khi giám khảo trùng model viết.
- [x] **Test**: model giả trả 503 rồi model dự phòng trả đúng; 429; timeout; key sai (401) không chuyển; cả hai cùng 503 thì chờ rồi thử lại; tiền tính đúng model đã trả lời.

> Cách làm: `with_overload_fallback` dùng `with_fallbacks` của LangChain với các lỗi chuẩn `ModelAPIError`, `ModelRateLimitError`, `ModelTimeoutError`, `ModelConnectionError` (cả Gemini và OpenAI đều ném các lỗi này). Áp cho model viết, giám khảo, rerank, prompt ảnh. Research agent chưa có dự phòng vì `create_agent` cần chat model thật; để sau nếu agent hay bị 503. Model dùng thật được ghi trong `Usage.by_model` (tiền tính theo đó); chưa log riêng mỗi lần chuyển.

## Tiêu chí hoàn thành

- [x] Model chính trả 503 thì run vẫn xong bằng model dự phòng; test giả lập 503/429/timeout xanh

---

[← Ngày 1](day-01.md) · [Mục lục](README.md) · [Ngày 3 →](day-03.md)
