# Ngày 7: Chạy thật, hoàn thiện, tài liệu

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Chạy cả hai chế độ, sửa lỗi, cập nhật tài liệu.

## Phụ thuộc / chuẩn bị

- Ngày 1–6 của bộ này

## Công việc

- [ ] **Chạy thật**: Script `scripts/run_scene_images.py --manual-dir` nạp ảnh từ thư mục; `run_media.py` dựng video 3 phút (~24 cảnh) từ ảnh manual.
- [ ] **Kiểm tra số ảnh**: Kiểm tra `scene_images_max=35` khi video dài hơn 3 phút; ghi nhận nếu cần nâng.
- [ ] **Sửa lỗi**: Hai nhánh cùng `interrupt` song song; nếu lỗi thì xếp tuần tự.
- [ ] **Tài liệu**: Cập nhật README và `docs/project-plan-v5.md` nếu cần; cập nhật bộ nhớ sở thích (tuỳ chọn) lưu lựa chọn auto/manual.

## Tiêu chí hoàn thành

- [ ] Video 3 phút từ ảnh manual đạt chuẩn như auto; test, ruff, mypy xanh

---

[← Ngày 6](day-06.md) · [Mục lục](README.md)
