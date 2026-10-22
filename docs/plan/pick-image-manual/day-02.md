# Ngày 2: API tải ảnh lên

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Endpoint nhận và kiểm tra ảnh người dùng tải, phục vụ lại để xem trước.

## Phụ thuộc / chuẩn bị

- Ngày 4 (RLS, chủ project)
- Ngày 17 (`GET /media`)

## Công việc

- [ ] **Endpoint**: `POST /projects/{id}/uploads` (multipart, 1 ảnh/lần; web gọi song song nhiều lần): xác thực chủ project như `get_media`.
- [ ] **Kiểm tra**: JPEG/PNG/WebP, ≤ 10 MB, mở được bằng Pillow, bỏ EXIF, đổi sang JPEG; ảnh nhỏ hơn 720×1280 hoặc lệch tỉ lệ thì trả cảnh báo (vẫn nhận, sẽ crop giữa).
- [ ] **Lưu**: `<media_dir>/uploads/<project_id>/<hash>.jpg`, trả `path` tương đối; mở rộng `GET /media` cho đường dẫn này; giới hạn ≤ 60 ảnh/project.
- [ ] **Test**: Đúng chủ, sai chủ, sai định dạng, quá nặng, path traversal, ảnh hỏng.

## Tiêu chí hoàn thành

- [ ] Tải ảnh lên được và xem lại qua `/media`; ảnh sai bị từ chối đúng mã lỗi

---

[← Ngày 1](day-01.md) · [Mục lục](README.md) · [Ngày 3 →](day-03.md)
