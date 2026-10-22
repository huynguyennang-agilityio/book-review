# Ngày 3: Bước chọn auto/manual

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Thêm bước hỏi một lựa chọn duy nhất và định tuyến graph.

## Phụ thuộc / chuẩn bị

- Ngày 15 (interrupt kịch bản)
- Ngày 11 (`estimate_cost`)

## Công việc

- [x] **State**: `RunOptions.image_mode: "auto"|"manual"` (mặc định auto).
- [x] **Node**: `choose_image_mode` (interrupt) sau `review_script`: payload gồm số nhân vật, số ảnh cảnh theo `image_plan`, giá auto ước tính; resume `{"mode"}` hoặc `{"cancel": true}`.
- [x] **Graph**: `build.py`: node mới nằm trước `character_sheets`; nhánh TTS chạy song song như cũ. Auto đi đúng đường cũ.
- [x] **Chi phí**: `estimate_cost` hiện phần tiết kiệm nếu manual.
- [x] **Test**: Auto không đổi hành vi (test hiện có vẫn xanh); huỷ khi đang chờ chọn.

## Tiêu chí hoàn thành

- [x] Chọn auto chạy y như cũ; chọn manual đi vào nhánh manual (chưa cần có UI)

---

[← Ngày 2](day-02.md) · [Mục lục](README.md) · [Ngày 4 →](day-04.md)
