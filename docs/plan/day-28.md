# Ngày 28: Đồng bộ thời lượng clip I2V trong timeline

> Giai đoạn 2: Chuyển động Hybrid · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Clip I2V khớp đúng thời lượng shot trong timeline tuyệt đối.

## Phụ thuộc / chuẩn bị

- Ngày 27

## Công việc

### Timeline

- [ ] Clip dài hơn shot thì cắt, ngắn hơn một chút thì làm chậm bằng `setpts`, ngắn nhiều thì nối Ken Burns từ frame cuối.
- [ ] Cập nhật test timeline và test thời lượng sau render.

## Đầu ra

- Logic đồng bộ thời lượng + test

## Tiêu chí hoàn thành

- [ ] Không có khoảng đen, hình khớp tiếng, test pass

---

[← Ngày 27](day-27.md) · [Mục lục](README.md) · [Ngày 29 →](day-29.md)
