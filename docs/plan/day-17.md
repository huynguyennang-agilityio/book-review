# Ngày 17: Màn duyệt nhân vật

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Người dùng chọn ảnh nhân vật trên web trước khi tạo ảnh cảnh.

## Phụ thuộc / chuẩn bị

- Ngày 16

## Công việc

### Graph

- [ ] Node `review_characters`: `interrupt()` trả ảnh ứng viên.
- [ ] Chạy song song nhánh âm thanh (tts_align → build_timeline → subtitles) với nhánh nhân vật như mục 2.1.

### Web

- [ ] Lưới 4 ảnh mỗi nhân vật, chọn 1 hoặc yêu cầu tạo lại (có ghi chú).

## Đầu ra

- Màn duyệt nhân vật
- Graph có nhánh song song

## Tiêu chí hoàn thành

- [ ] Chọn nhân vật trên web rồi graph chạy tiếp tới scene_images

---

[← Ngày 16](day-16.md) · [Mục lục](README.md) · [Ngày 18 →](day-18.md)
