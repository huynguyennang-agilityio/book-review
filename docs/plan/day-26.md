# Ngày 26: Chọn shot animate, chạy song song, fallback

> Giai đoạn 2: Chuyển động Hybrid · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Animate hook và 3–5 cảnh song song, lỗi I2V không làm dừng graph.

## Phụ thuộc / chuẩn bị

- Ngày 25

## Công việc

### Node `motion`

- [ ] Chọn shot cần animate (hook + 3–5 cảnh có hành động), cấu hình được số cảnh.
- [ ] Chạy song song có giới hạn bằng `Semaphore`.
- [ ] I2V lỗi hoặc timeout thì tự chuyển sang Ken Burns.

## Đầu ra

- Node motion bản hybrid

## Tiêu chí hoàn thành

- [ ] Lỗi I2V (giả lập) không làm dừng graph

---

[← Ngày 25](day-25.md) · [Mục lục](README.md) · [Ngày 27 →](day-27.md)
