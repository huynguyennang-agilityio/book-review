# Ngày 3: Nối vào graph, chạy thật, eval, tài liệu

> Tính năng viết kịch bản bằng OpenAI · Nguồn: [plan OpenAI + dự phòng](README.md)

## Mục tiêu

Web dùng OpenAI viết kịch bản, có dự phòng; chất lượng bám nguồn không giảm.

## Phụ thuộc / chuẩn bị

- Ngày 1–2 của bộ này
- Người dùng đồng ý chạy eval (dưới 1 USD)

## Công việc

- [ ] **Graph**: `graph/live.py` dùng model viết (OpenAI + dự phòng) cho `storyboard`, `rewrite_scene`, phần sửa cảnh của `faithfulness_eval`; giám khảo dùng Gemini + dự phòng; các node khác dùng Gemini + dự phòng.
- [ ] **Script**: `run_storyboard.py`, `run_scene_images.py`, `evals/run_ragas.py` đọc cùng cấu hình.
- [ ] **Docker**: truyền `OPENAI_API_KEY` vào `api`; build lại và chạy một video 3 phút từ web.
- [ ] **Eval**: chạy faithfulness trên 10 sách golden, so với baseline Gemini trong `docs/evals/`; nếu < 0,9 thì chỉnh prompt hoặc quay về `WRITER_PROVIDER=gemini`.
- [ ] **Tài liệu**: README, `.env.example`, `CLAUDE.md` (key mới), `docs/project-plan-v5.md` mục model; ghi quyết định vào `docs/decisions/`.

## Tiêu chí hoàn thành

- [ ] Video từ web dùng OpenAI viết; faithfulness ≥ 0,9 trên bộ golden; README, `.env.example` cập nhật

---

[← Ngày 2](day-02.md) · [Mục lục](README.md)
