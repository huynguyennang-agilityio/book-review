# Ngày 27: Chuẩn hóa clip và chi phí I2V ở checkpoint

> Giai đoạn 2: Chuyển động Hybrid · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Mọi clip về đúng 720×1280@30fps và người dùng thấy chi phí I2V trước khi duyệt.

## Phụ thuộc / chuẩn bị

- Ngày 26

## Công việc

### Chuẩn hóa

- [ ] FFmpeg chuẩn hóa fps, kích thước, pixel format cho clip I2V.

### Chi phí

- [ ] `estimate_cost` thêm phần I2V, hiển thị ở màn duyệt kịch bản, chặn theo ngân sách.

## Đầu ra

- Chuẩn hóa clip + hiển thị chi phí I2V

## Tiêu chí hoàn thành

- [ ] Lỗi I2V không làm dừng graph, chi phí I2V hiện ở checkpoint

---

[← Ngày 26](day-26.md) · [Mục lục](README.md) · [Ngày 28 →](day-28.md)
