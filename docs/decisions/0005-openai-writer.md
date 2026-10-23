# ADR 0005: OpenAI viết kịch bản, Gemini chấm, dự phòng khi quá tải

- Trạng thái: Chấp nhận
- Ngày: 2026-10-23
- Liên quan: [plan OpenAI + dự phòng](../plan/openai-writer/README.md), `providers/llm_writer.py`, `providers/fallback.py`

## Quyết định

- Có `OPENAI_API_KEY` thì `gpt-5.4-mini` viết storyboard, viết lại cảnh và sửa cảnh điểm thấp (`WRITER_PROVIDER=auto`). Không có key thì Gemini viết như cũ.
- Giám khảo faithfulness giữ Gemini `gemini-3.1-flash-lite`: khác hãng với model viết nên không tự chấm cho mình. Research, rerank, prompt ảnh, embeddings giữ Gemini.
- Lỗi quá tải (`ModelAPIError`, `ModelRateLimitError`, `ModelTimeoutError`, `ModelConnectionError` của langchain-core: 503/5xx, 429, timeout) thì chuyển ngay sang model dự phòng: model viết → `gemini-3.5-flash-lite`, giám khảo → `gemini-3.5-flash-lite`, rerank/prompt ảnh → `gemini-3.1-flash-lite`. Lỗi khác không chuyển.
- Chi phí tính theo model thực sự trả lời (`Settings.model_prices`).

## Kết quả eval (2026-10-23, 20 sách golden, video 3 phút)

Báo cáo: [`docs/evals/eval_report_gpt-5.4-mini.json`](../evals/eval_report_gpt-5.4-mini.json).

| context + body | Số cảnh | Bộ chấm tiếng Việt | RAGAS gốc |
| --- | --- | --- | --- |
| Lần viết đầu | 226 | **0.942** | 0.862 |
| Sau vòng sửa | 226 | 1.000 | 0.895 |

- 19/20 sách ra storyboard; *Hoàng tử bé* thất bại vì một quote ở phần body không khớp nguyên văn sau 3 lần viết.
- 29/226 cảnh (13%) phải viết lại; sau vòng sửa không còn cảnh `LOW_FAITHFULNESS`.
- Trung bình 18,9 cảnh/sách; storyboard ~0,016–0,021 USD/sách, giám khảo ~0,005 USD/sách.
- Không so trực tiếp được với baseline Gemini trong `eval_report.json` (7,2 cảnh/sách, cấu hình video ~45 giây trước PR #44): kịch bản dài gấp ~2,6 lần nên có nhiều chỗ để lệch nguồn hơn.

## Giới hạn đã biết

- Research agent chưa có dự phòng (`create_agent` cần chat model thật).
- Giám khảo và model viết cùng rơi về `gemini-3.5-flash-lite` khi cả OpenAI và giám khảo cùng quá tải: hiếm, chưa chặn.
- RAGAS chạy với giám khảo không bọc dự phòng (RAGAS cần chat model thật).
