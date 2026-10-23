# Ngày 1: Sửa thiếu cảnh ở tab "Từ tên sách"

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Video 3 phút ra đủ ~24 cảnh và đúng thời lượng, thay vì 17–18 cảnh (~2 phút 10 giây).

## Phụ thuộc / chuẩn bị

- PR #44 (`section_max_scenes`, `_scene_count_hint`)
- Ngày 10 (storyboard có citation), ngày 22 (faithfulness > 0,9)

## Công việc

- [x] **Ép tối thiểu**: trong `storyboard/writer.py` `write_section`, sau `_resolve`, nếu số cảnh < 90% mục tiêu của phần thì thêm vào `problems` ("Phần body mới có 7 cảnh, cần ít nhất 10; tách ý dài thành nhiều cảnh") để vòng retry có sẵn viết lại.
- [x] **Nguyên nhân gốc** (tìm thấy khi làm): `SectionDraft` giới hạn 6 cảnh mỗi lần trả lời, trong khi `body` của video 3 phút cần 11 cảnh, nên cả kịch bản tối đa 1 + 6 + 6 + 6 = 19 cảnh; trừ cảnh bị bỏ vì thiếu citation thì còn 17–18. Nâng trần lên 25 (`MAX_DRAFT_SCENES`), số cảnh vẫn bị cắt theo `section_max_scenes`.
- [x] **Viết lại vẫn thiếu**: dùng bản hợp lệ dài nhất trong các lần viết thay vì làm hỏng run. Bỏ ý tách cảnh dài làm hai: tách chỉ tăng số cảnh, không làm video dài thêm.
- [x] **Chia phần 1:4:1** (thay 2:4:2): video 3 phút ra hook 1, bối cảnh 4, nội dung 15, nhận xét + CTA 4, khớp mục 1 plan v5. Chạy thật lần 1 với 2:4:2 cho CTA 6 cảnh và body chỉ 11 cảnh.
- [x] **Không lặp ý giữa các phần**: prompt mỗi phần kèm lời đọc các cảnh đã viết ở phần trước (lần 1 body kể lại phần giới thiệu nhân vật của context).
- [x] **Cờ `SHORT_SCRIPT`**: tổng thời lượng ước tính < 90% mục tiêu thì gắn cờ ở storyboard, kèm `target_seconds`, `estimated_seconds`.
- [x] **Ước lượng thời lượng**: `storyboard/duration.py` có `estimate_seconds(text)` tính theo số âm tiết (~3,8 âm tiết/giây theo số đo spike ngày 1, Ngày 5 đo lại). Writer kiểm **tổng thời lượng** ±10%, không chỉ đếm cảnh.
- [x] **Prompt `storyboard_v3.md`**: bỏ "body 2–4 cảnh, mỗi cảnh 1–2 câu" viết cứng, số cảnh và số câu do code truyền vào; cập nhật `PROMPT_VERSION`.
- [x] **Web**: `ScriptReview.tsx` luôn hiện "Thời lượng ≈ m:ss (mục tiêu m:ss)", tính lại theo lời đọc đang sửa, tô đỏ khi ngắn hơn 90% mục tiêu.
- [x] **Test**: thiếu cảnh rồi đủ ở lần viết lại ra 24 cảnh; đủ cảnh nhưng lời quá ngắn cũng bị viết lại; luôn thiếu thì giữ bản dài nhất và có cờ; `estimate_seconds` ở Python và TS cho cùng số.
- [ ] **Chạy thật (Mac)**: `run_storyboard.py nha-gia-kim sapiens`, rồi `evals/run_ragas.py`.

## Tiêu chí hoàn thành

- [ ] Video 3 phút ra ~24 cảnh, thời lượng ước tính 2:45–3:15
- [ ] Faithfulness golden vẫn > 0,9

---

[Mục lục](README.md) · [Ngày 2 →](day-02.md)
