# Ngày 18: Ảnh cảnh thật, tái dùng ảnh, fallback an toàn

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Thay ảnh placeholder bằng ảnh cảnh thật, nhân vật nhất quán, không bị kẹt khi ảnh bị bộ lọc chặn.

## Phụ thuộc / chuẩn bị

- Ngày 17

## Công việc

### Node `scene_images`

- [ ] 25–35 ảnh mỗi video, 1 ảnh dùng cho 2–3 shot (`Shot.image_ref`).
- [ ] Tạo theo tỷ lệ gần 9:16 (bội số 16) rồi crop chính xác 720×1280.
- [ ] Tối đa 2 nhân vật mỗi khung, truyền ảnh tham chiếu đã duyệt.
- [ ] Ảnh bị bộ lọc chặn thì đổi sang cảnh `metaphor` và tạo lại.
- [ ] Cache theo hash prompt + seed, chạy lại không tạo lại ảnh đã có.

### Kiểm tra

- [ ] Chạy 2 sách đầy đủ, chấm tay độ nhận ra nhân vật.

## Đầu ra

- Video có ảnh thật của 2 sách mẫu

## Tiêu chí hoàn thành

- [ ] Nhân vật nhận ra được ở ≥ 80% cảnh

---

[← Ngày 17](day-17.md) · [Mục lục](README.md) · [Ngày 19 →](day-19.md)
