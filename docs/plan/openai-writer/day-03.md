# Ngày 3: Nối vào graph, chạy thật, eval, tài liệu

> Tính năng viết kịch bản bằng OpenAI · Nguồn: [plan OpenAI + dự phòng](README.md)

## Mục tiêu

Web dùng OpenAI viết kịch bản, có dự phòng; chất lượng bám nguồn không giảm.

## Phụ thuộc / chuẩn bị

- Ngày 1–2 của bộ này
- Người dùng đồng ý chạy eval (dưới 1 USD)

## Công việc

- [x] **Graph**: `graph/live.py` dùng model viết (OpenAI + dự phòng) cho `storyboard`, `rewrite_scene`, phần sửa cảnh của `faithfulness_eval`; giám khảo dùng Gemini + dự phòng; các node khác dùng Gemini + dự phòng.
- [x] **Script**: `run_storyboard.py`, `run_scene_images.py`, `evals/run_ragas.py` đọc cùng cấu hình.
- [ ] **Docker**: truyền `OPENAI_API_KEY` vào `api`; build lại và chạy một video 3 phút từ web.
- [x] **Eval**: chạy faithfulness trên 10 sách golden, so với baseline Gemini trong `docs/evals/`; nếu < 0,9 thì chỉnh prompt hoặc quay về `WRITER_PROVIDER=gemini`.
- [x] **Tài liệu**: README, `.env.example`, `CLAUDE.md` (key mới), `docs/project-plan-v5.md` mục model; ghi quyết định vào `docs/decisions/`.

> Kết quả: [ADR 0005](../../decisions/0005-openai-writer.md). Faithfulness context+body lần viết đầu 0.942, sau vòng sửa 1.000 (20 sách, 19 ra storyboard). Sửa thêm: trích sai ở hook/review_cta không còn làm hỏng cả kịch bản.

## Tiêu chí hoàn thành

- [ ] Video từ web dùng OpenAI viết; faithfulness ≥ 0,9 trên bộ golden; README, `.env.example` cập nhật

---

[← Ngày 2](day-02.md) · [Mục lục](README.md)
