# Ngày 1: Sửa thiếu cảnh ở tab "Từ tên sách"

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Video 3 phút ra đủ ~24 cảnh và đúng thời lượng, thay vì 17–18 cảnh (~2 phút 10 giây).

## Phụ thuộc / chuẩn bị

- PR #44 (`section_max_scenes`, `_scene_count_hint`)
- Ngày 10 (storyboard có citation), ngày 22 (faithfulness > 0,9)

## Công việc

- [ ] **Ép tối thiểu**: trong `storyboard/writer.py` `write_section`, sau `_resolve`, nếu số cảnh < 90% mục tiêu của phần thì thêm vào `problems` ("Phần body mới có 7 cảnh, cần ít nhất 10; tách ý dài thành nhiều cảnh") để vòng retry có sẵn viết lại.
- [ ] **Bù cảnh**: retry hết lượt mà vẫn thiếu thì tách cảnh dài nhất (≥ 3 câu) thành 2 cảnh, giữ nguyên citation, không gọi LLM.
- [ ] **Cờ `SHORT_SCRIPT`**: vẫn thiếu sau khi tách thì gắn cờ ở storyboard, kèm thời lượng ước tính.
- [ ] **Ước lượng thời lượng**: `storyboard/duration.py` có `estimate_seconds(text)` tính theo số âm tiết (~4,2 âm tiết/giây, Ngày 5 đo lại). Writer kiểm **tổng thời lượng** ±10%, không chỉ đếm cảnh.
- [ ] **Prompt `storyboard_v3.md`**: bỏ "body 2–4 cảnh, mỗi cảnh 1–2 câu" viết cứng, số cảnh và số câu do code truyền vào; cập nhật `PROMPT_VERSION`.
- [ ] **Web**: `ScriptReview.tsx` hiện "Kịch bản ≈ X phút, ngắn hơn mục tiêu Y phút" khi có `SHORT_SCRIPT`.
- [ ] **Test**: model giả trả 17 cảnh rồi đủ cảnh ở lần retry thì ra ≥ 22 cảnh; model giả luôn thiếu thì tách cảnh và có cờ; `estimate_seconds` với câu mẫu.
- [ ] **Chạy thật (Mac)**: `run_storyboard.py nha-gia-kim sapiens`, rồi `evals/run_ragas.py`.

## Tiêu chí hoàn thành

- [ ] Video 3 phút ra ~24 cảnh, thời lượng ước tính 2:45–3:15
- [ ] Faithfulness golden vẫn > 0,9

---

[Mục lục](README.md) · [Ngày 2 →](day-02.md)
