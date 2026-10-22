# Ngày 4: Web: tab, form 3 ô, tải file

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Từ web dán bài (hoặc tải file) rồi chạy tới video, tab cũ không đổi.

## Phụ thuộc / chuẩn bị

- Ngày 3 (node `ingest_review`)
- Ngày 14–15 (form, tiến độ, màn duyệt kịch bản)

## Công việc

- [ ] **Tab**: `page.tsx` thêm thanh **"Từ tên sách" | "Từ bài review có sẵn"**; khoá đổi tab khi đang chạy hoặc chờ duyệt; nhớ tab lần trước trong `localStorage`.
- [ ] **Form** `_components/ReviewTextForm.tsx`:
  - Tên sách (bắt buộc), tác giả và series (tùy chọn).
  - Ô Hook có đếm từ và cảnh báo khi > 20 từ; ô Ý chính bắt buộc; ô Nhận xét.
  - Dòng "≈ X phút Y giây video" cập nhật khi gõ.
  - Giọng đọc và ngân sách dùng chung với `BookForm`.
  - Dòng nhắc "Bạn chịu trách nhiệm về nội dung và bản quyền của bài review".
  - Lưu nháp 3 ô trong `localStorage`.
- [ ] **Tải file**: nút chọn `.txt`/`.md` (≤ 200 KB, UTF-8). Nội dung vào Ý chính; `.md` có đủ `## Hook` / `## Ý chính` / `## Nhận xét` thì tách vào 3 ô.
- [ ] **Thời lượng**: `_lib/duration.ts` cùng công thức với `estimate_seconds` của Python (test so số với vài câu mẫu).
- [ ] **Run**: `_lib/run.ts`:
  - `start()` nhận `source` và `userReview`; `lastStartRef` lưu cả hai để "Thử lại" chạy đúng tab.
  - `visibleNodes()` ẩn "Research" và "Xác nhận sách", thêm "Đọc bài review".
- [ ] **Màn duyệt** `ScriptReview.tsx`:
  - Nguồn hiện 3 khối Hook / Ý chính / Nhận xét, tô câu nguồn của từng cảnh.
  - Đánh dấu chỗ đổi số thành chữ.
  - Thay điểm faithfulness bằng chữ "Nguyên văn".
  - Ẩn nút "viết lại bằng AI", giữ nút sửa tay.
- [ ] **Test**: tách file `.md` theo tiêu đề, file quá 200 KB, đếm thời lượng, `visibleNodes`, lint và build web.

## Tiêu chí hoàn thành

- [ ] Trên web: dán bài → duyệt kịch bản → chọn ảnh auto hoặc manual → có video
- [ ] Tab "Từ tên sách" chạy như trước

---

[← Ngày 3](day-03.md) · [Mục lục](README.md) · [Ngày 5 →](day-05.md)
