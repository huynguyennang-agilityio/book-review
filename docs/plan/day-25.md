# Ngày 25: VideoProvider (I2V qua Fal)

> Giai đoạn 2: Chuyển động Hybrid · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Tạo được 1 clip 9:16 từ ảnh bằng Kling hoặc Hailuo, resume và hủy được.

## Phụ thuộc / chuẩn bị

- Quyết định làm Phase 2 sau giai đoạn đăng thử

## Công việc

### Provider

- [ ] `providers/video_fal.py`: `VideoProvider` interface, submit, poll, lấy kết quả.
- [ ] Lưu `job_id` vào `fal_job_ids` trong state ngay khi submit.
- [ ] Resume: nếu có `job_id` thì poll tiếp thay vì submit lại. Hủy: gọi cancel của Fal.

## Đầu ra

- Provider + test với provider giả lập

## Tiêu chí hoàn thành

- [ ] Tạo được 1 clip 9:16, resume và hủy được

---

[← Ngày 24](day-24.md) · [Mục lục](README.md) · [Ngày 26 →](day-26.md)
