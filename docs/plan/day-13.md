# Ngày 13: Walking skeleton media: phụ đề, Ken Burns, compose

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Có video thô từ đầu tới cuối, hình khớp tiếng và phụ đề, tạo ra từ graph.

## Phụ thuộc / chuẩn bị

- Ngày 12

## Công việc

### Phụ đề

- [x] `media/subtitles.py`: `.ass` theo thời gian tuyệt đối, cụm 20–25 ký tự, vị trí 60–70% chiều cao, xuất thêm `.srt`.

### Hình

- [x] Ảnh placeholder (màu + chữ) cho mỗi shot.
- [x] `media/kenburns.py` theo cách đã chốt ở ngày 1.

### Compose

- [x] `media/ffmpeg.py`: ghép `xfade` (bù phần chồng), đặt audio theo offset tuyệt đối, burn phụ đề ở pass cuối.
- [x] Node `compose_render` gửi job, chờ kết quả, lưu asset lên storage.

### Kiểm tra sau render

- [x] Test: thời lượng hình khớp tiếng (lệch ≤ 50ms), không có frame đen ngoài cảnh `title`.

## Đầu ra

- Video thô 720×1280@30fps từ một lần chạy graph
- Test thời lượng tự động

## Tiêu chí hoàn thành

- [x] Video thô khớp tiếng và phụ đề từ đầu tới cuối, được tạo từ graph

## Ghi chú

- Đây là mốc walking skeleton: mọi phần đã nối với nhau, các ngày sau chỉ thay phần giả bằng phần thật.

---

[← Ngày 12](day-12.md) · [Mục lục](README.md) · [Ngày 14 →](day-14.md)
