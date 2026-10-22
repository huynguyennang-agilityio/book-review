# Ngày 3: Chia cảnh nguyên văn và node `ingest_review`

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Từ 3 ô ra storyboard hợp lệ, lời đọc đúng nguyên văn, run dừng ở màn duyệt kịch bản.

## Phụ thuộc / chuẩn bị

- Ngày 2 (state, rẽ nhánh graph), ngày 1 (`estimate_seconds`)
- 3 bài review mẫu (xem [README](README.md))

## Công việc

- [ ] **Chia cảnh** `storyboard/verbatim.py`, code thuần:
  - `split_review_into_scenes(hook, main, comment)`: Hook → 1 cảnh `hook`; Ý chính → nhiều cảnh `body`; Nhận xét → cảnh `review_cta`. Tách câu (`. ! ? …`, chữ viết tắt, ngoặc kép), gom 2–3 câu ~7 giây, không vượt ranh giới đoạn văn. Ô trống thì không có cảnh của phần đó.
- [ ] **Chuẩn hoá cho TTS** `normalize_for_tts(text)`:
  - Số thành chữ ("3" → "ba", "1.200" → "một nghìn hai trăm"), "%" thành "phần trăm", vài chữ viết tắt thường gặp.
  - Bỏ cú pháp markdown.
  - Trả kèm danh sách chỗ đã đổi để màn duyệt đánh dấu.
- [ ] **Kiểm tra nguyên văn** `verbatim_check`: ghép lời đọc lại rồi so với văn bản gốc đã chuẩn hoá. Khớp thì `eval_scores.faithfulness = 1.0`. Lệch là lỗi code nên báo `INTERNAL_ERROR`.
- [ ] **Nguồn và citation**: nạp 3 ô vào RAG bằng `ingest_text` (`source_id = user_review:<hash>`, 3 tài liệu Hook / Ý chính / Nhận xét); mỗi cảnh trích chính câu nguồn của nó để `sources.md` và màn duyệt nguồn dùng lại.
- [ ] **Metadata** `storyboard/review_meta.py`: một lời gọi Gemini (structured output) trả `ReviewMeta`:
  - `kind`, `genre_ok`.
  - Mỗi cảnh: `scene_type`, `mood`, `on_screen_text_vi` (≤ 8 từ, rút từ câu của cảnh).
  - `characters` (1–3, chỉ sách hư cấu; thiếu mô tả ngoại hình thì AI gợi ý và gắn `appearance_guessed`).
  - `style_prompt_en`, `caption_vi`, `hashtags`.
  - Model không được trả lời đọc; code bỏ mọi trường lạ. Văn bản người dùng nằm trong khối "chỉ là dữ liệu".
- [ ] **Node** `graph/nodes/review_text.py` `ingest_review`: ghép các bước trên thành `state.research` (cùng định dạng research agent) và `state.storyboard`, đi thẳng `estimate_cost` (bỏ qua `storyboard` và `faithfulness_eval`).
- [ ] **Script**: `scripts/run_review_text.py <file.md|.txt> --title ...` chạy tới hết storyboard, in số cảnh, thời lượng ước tính, chi phí.
- [ ] **Test**: chỉ Ý chính / đủ 3 ô / hook trống / nhận xét trống; ghép lời đọc = văn bản gốc (không mất, thêm hay đảo câu); 450 từ → ~3 phút, ~24 cảnh; `ReviewMeta` giả trả thêm lời đọc thì bị bỏ; câu "bỏ qua hướng dẫn trên…" không ảnh hưởng metadata.
- [ ] **Chạy thật (Mac)**: 3 bài mẫu, ghi số cảnh, thời lượng ước tính, chi phí Gemini.

## Tiêu chí hoàn thành

- [ ] Run tab mới dừng ở `review_script` với storyboard đúng nguyên văn
- [ ] Chi phí Gemini mỗi bài dưới 0,01 USD

---

[← Ngày 2](day-02.md) · [Mục lục](README.md) · [Ngày 4 →](day-04.md)
