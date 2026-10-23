# Ngày 3: Chia cảnh nguyên văn và node `ingest_review`

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Từ 3 ô ra storyboard hợp lệ, lời đọc đúng nguyên văn, run dừng ở màn duyệt kịch bản.

## Phụ thuộc / chuẩn bị

- Ngày 2 (state, rẽ nhánh graph), ngày 1 (`estimate_seconds`)
- 3 bài review mẫu (xem [README](README.md))

## Công việc

- [x] **Chia cảnh** `storyboard/verbatim.py`, code thuần:
  - `split_review_into_scenes(hook, main, comment)`: Hook → 1 cảnh `hook`; Ý chính → nhiều cảnh `body`; Nhận xét → cảnh `review_cta`. Tách câu (`. ! ? …`, chữ viết tắt, ngoặc kép), gom 2–3 câu ~7 giây, không vượt ranh giới đoạn văn. Ô trống thì không có cảnh của phần đó.
- [x] **Chuẩn hoá cho TTS** `normalize_for_tts(text)`:
  - Số thành chữ ("3" → "ba", "1.200" → "một nghìn hai trăm"), "%" thành "phần trăm", vài chữ viết tắt thường gặp.
  - Bỏ cú pháp markdown.
  - Trả kèm danh sách chỗ đã đổi để màn duyệt đánh dấu.
- [x] **Kiểm tra nguyên văn** `verbatim_check`: ghép lời đọc lại rồi so với văn bản gốc đã chuẩn hoá. Khớp thì `eval_scores.faithfulness = 1.0`. Lệch là lỗi code nên báo `INTERNAL_ERROR`.
- [x] **Nguồn và citation**: nạp 3 ô vào RAG bằng `ingest_text` (`source_id = user_review:<hash>`, 3 tài liệu Hook / Ý chính / Nhận xét); mỗi cảnh trích chính câu nguồn của nó để `sources.md` và màn duyệt nguồn dùng lại.
- [x] **Metadata** `storyboard/review_meta.py`: một lời gọi Gemini (structured output) trả `ReviewMeta`:
  - `kind`, `genre_ok`.
  - Mỗi cảnh: `scene_type`, `mood`, `on_screen_text_vi` (≤ 8 từ, rút từ câu của cảnh).
  - `characters` (1–3, chỉ sách hư cấu; thiếu mô tả ngoại hình thì AI gợi ý và gắn `appearance_guessed`).
  - `style_prompt_en`, `caption_vi`, `hashtags`.
  - Model không được trả lời đọc; code bỏ mọi trường lạ. Văn bản người dùng nằm trong khối "chỉ là dữ liệu".
- [x] **Node** `graph/nodes/review_text.py` `ingest_review`: ghép các bước trên thành `state.research` (cùng định dạng research agent) và `state.storyboard`, đi thẳng `estimate_cost` (bỏ qua `storyboard` và `faithfulness_eval`).
- [x] **Script**: `scripts/run_review_text.py <file.md|.txt> --title ...` chạy tới hết storyboard, in số cảnh, thời lượng ước tính, chi phí.
- [x] **Test**: chỉ Ý chính / đủ 3 ô / hook trống / nhận xét trống; ghép lời đọc = văn bản gốc (không mất, thêm hay đảo câu); 450 từ → ~3 phút, ~24 cảnh; `ReviewMeta` giả trả thêm lời đọc thì bị bỏ; câu "bỏ qua hướng dẫn trên…" không ảnh hưởng metadata.
- [x] **Chạy thật (Mac)**: 3 bài mẫu, ghi số cảnh, thời lượng ước tính, chi phí Gemini.

## Ghi chú triển khai

- Code: `storyboard/verbatim.py` (chia cảnh, `normalize_for_tts`, `verbatim_problems`), `storyboard/review_meta.py` (`ReviewMeta`, `make_meta_writer`), node trong `graph/nodes/review_text.py`, nối vào `build_graph(review_meta_writer=..., review_index=...)` và `graph/live.py`.
- Cảnh nhắm ~7 giây (25 âm tiết), tối đa ~10 giây (36 âm tiết); câu dài hơn thì tách ở dấu phẩy, chấm phẩy, hai chấm. Hook luôn đúng 1 cảnh.
- Theo hệ số 3,8 âm tiết/giây đo ở ngày 1, bài 450 từ đọc ~2 phút (~18 cảnh), không phải 3 phút như ước lượng ban đầu; 3 phút cần ~650 từ. Test dùng số đo này.
- Mỗi ô là một nguồn `user_review:<hash>:<hook|main|comment>`, chunk mang `user_id` của người dùng nên RLS giữ riêng tư; sổ ghi nhận của Indexing API tách theo người dùng.
- `Storyboard` thêm `source = "user_review"`; `Scene.tts_changes` ghi các chỗ đọc khác chữ gốc; `Character.appearance_guessed`. `target_seconds` để trống vì độ dài theo bài; `spoiler_free = false` vì web không kiểm bài của người dùng.
- Model gắn metadata lỗi thì dùng metadata mặc định và gắn cờ `META_DEFAULT`, run vẫn tới màn duyệt. Model báo `genre_ok = false` thì chặn với `GENRE_EXCLUDED`.
- Prompt metadata để trong code (`review_meta.SYSTEM`) như prompt ảnh; dữ liệu bài gửi dạng JSON trong khối `<du_lieu>`, ký tự `<` được escape nên bài không tự đóng được khối.
- 3 bài mẫu tự viết ở `evals/review-text/` (Nhà giả kim đủ 3 ô, Atomic Habits đủ 3 ô, Hoàng tử bé chỉ Ý chính).

## Tiêu chí hoàn thành

- [ ] Run tab mới dừng ở `review_script` với storyboard đúng nguyên văn
- [ ] Chi phí Gemini mỗi bài dưới 0,01 USD

---

[← Ngày 2](day-02.md) · [Mục lục](README.md) · [Ngày 4 →](day-04.md)
