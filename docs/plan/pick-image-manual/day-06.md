# Ngày 6: Web: trang tải ảnh manual

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Trang một lượt cho nhân vật và ảnh cảnh.

## Phụ thuộc / chuẩn bị

- Ngày 5 của bộ này

## Công việc

- [ ] **Giao diện**: `ManualImages.tsx`: phần nhân vật (prompt, ô tải 1 ảnh) và phần cảnh theo từng cảnh (lời đọc rút gọn, prompt, ô tải, xem trước 9:16).
- [ ] **Tiện ích**: Sao chép từng prompt, sao chép tất cả, tải file prompt; kéo thả nhiều file gán theo thứ tự có bước xác nhận; thay ảnh trước khi tiếp tục.
- [ ] **Trạng thái**: Thanh "đã tải 18/28", nút "Tiếp tục dựng video" chỉ bật khi đủ; lỗi từng ô hiện tại ô.
- [ ] **Lưu ý**: Dòng nhắc: người dùng chịu trách nhiệm về độ liền mạch và bản quyền ảnh.

## Tiêu chí hoàn thành

- [ ] Tải đủ ảnh trên web thì graph chạy tiếp

---

[← Ngày 5](day-05.md) · [Mục lục](README.md) · [Ngày 7 →](day-07.md)
