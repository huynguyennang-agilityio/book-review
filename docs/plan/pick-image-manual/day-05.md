# Ngày 5: Web: chọn chế độ và client tải ảnh

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Màn chọn auto/manual và hook tải ảnh.

## Phụ thuộc / chuẩn bị

- Ngày 2 và 3 của bộ này
- Ngày 15

## Công việc

- [ ] **`run.ts`**: Nhận `Pending.type` mới `choose_image_mode` và `upload_images`, thêm bước tiến độ; hàm `uploadImage(file) → path`.
- [ ] **`ImageModeChoice.tsx`**: Thẻ hỏi auto/manual, nêu ~N ảnh và giá ~$X cho auto, ~M ảnh phải chuẩn bị cho manual; nút Tiếp tục.
- [ ] **Logic**: `_lib/images.ts`: parse payload, kiểm tra đủ ảnh, gán nhiều file theo thứ tự, trạng thái từng ô.
- [ ] **Test**: Test logic `_lib` như `characters.ts` hiện có.

## Tiêu chí hoàn thành

- [ ] Trên web chọn được chế độ và tải thử một ảnh lên

---

[← Ngày 4](day-04.md) · [Mục lục](README.md) · [Ngày 6 →](day-06.md)
