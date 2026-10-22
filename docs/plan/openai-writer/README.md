# Viết kịch bản bằng OpenAI, dự phòng Gemini khi quá tải

Tính năng: model viết kịch bản chuyển từ Gemini sang OpenAI (**GPT-5.4 mini**). Khi một model bị quá tải hoặc lỗi tạm thời, app tự chuyển sang model dự phòng thay vì dừng run.

## Phân công model

| Việc | Model chính | Dự phòng khi quá tải |
| --- | --- | --- |
| Viết kịch bản (`storyboard`), viết lại cảnh (`rewrite_scene`, sửa cảnh điểm thấp trong `faithfulness_eval`) | OpenAI `gpt-5.4-mini` | Gemini `gemini-3.5-flash-lite` |
| Chấm faithfulness (giám khảo) | Gemini `gemini-3.1-flash-lite` | Gemini `gemini-3.5-flash-lite` |
| Research agent, xác nhận sách, rerank, prompt ảnh | Gemini `gemini-3.5-flash-lite` (giữ nguyên) | Gemini `gemini-3.1-flash-lite` |
| Embeddings RAG | Gemini `gemini-embedding-001` (giữ nguyên) | không đổi (đổi phải nạp lại toàn bộ kho) |

- **Quá tải** = HTTP 503, 429 (rate limit), 500/502/504 và timeout. Lỗi 4xx khác (key sai, request sai) không chuyển model mà báo lỗi ngay.
- Chuyển ngay ở lần lỗi đầu tiên sang model dự phòng; nếu cả hai cùng lỗi thì mới dùng vòng chờ 15s/30s/60s hiện có.
- Không có `OPENAI_API_KEY` thì app chạy y như cũ (Gemini viết kịch bản). Đặt `WRITER_PROVIDER=gemini` để quay lại Gemini mà không đổi code.
- Giám khảo và model viết luôn khác nhau. Trường hợp hiếm cả hai cùng rơi về `gemini-3.5-flash-lite` thì ghi cảnh báo vào log và metadata run.
- Chi phí: tính theo model thực sự trả lời (bảng giá theo model trong config), không còn một giá cho mọi lời gọi.

Ước lượng 3 ngày làm việc, mỗi ngày một PR nhỏ có test.

| Ngày | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- |
| [1](day-01.md) | Provider OpenAI và bảng giá theo model | Viết được storyboard 1 sách golden bằng `gpt-5.4-mini`, citation hợp lệ, chi phí đúng giá OpenAI |
| [2](day-02.md) | Dự phòng khi quá tải | Model chính trả 503 thì run vẫn xong bằng model dự phòng; test giả lập 503/429/timeout xanh |
| [3](day-03.md) | Nối vào graph, chạy thật, eval, tài liệu | Video từ web dùng OpenAI viết; faithfulness ≥ 0,9 trên bộ golden; README, `.env.example` cập nhật |

## Cần từ người dùng

- `OPENAI_API_KEY` (API key ở platform.openai.com, không phải gói ChatGPT) thêm vào `.env` trên Mac.
- Đồng ý chạy eval faithfulness ở ngày 3 (vài chục lời gọi Gemini + OpenAI, dưới 1 USD).

[← Mục lục kế hoạch](../README.md)
