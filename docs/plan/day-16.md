# Ngày 16: Sheet nhân vật

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Tạo sheet tham chiếu nhiều góc cho từng nhân vật bằng model ảnh đã chọn.

## Phụ thuộc / chuẩn bị

- Ngày 1 (model ảnh)
- Ngày 15

## Công việc

### Provider

- [ ] `providers/image_fal.py`: `ImageProvider` interface, gọi model đã chốt, `Semaphore`, lưu `fal_job_ids` để hủy được.

### Node

- [ ] `character_sheets`: 4 ứng viên mỗi nhân vật chính, seed cố định, prompt có `no text`.
- [ ] Tái dùng nhân vật đã duyệt từ Store nếu là cùng series.
- [ ] Cộng chi phí vào state, dừng khi vượt ngân sách.

## Đầu ra

- Node character_sheets + test với provider giả lập

## Tiêu chí hoàn thành

- [ ] Sinh được 4 ứng viên cho mỗi nhân vật của 2 sách mẫu

---

[← Ngày 15](day-15.md) · [Mục lục](README.md) · [Ngày 17 →](day-17.md)
