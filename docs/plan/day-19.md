# Ngày 19: Hoàn thiện compose và màn kết quả

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Video đạt chuẩn đăng TikTok, Shorts, Reels và người dùng tải được mọi đầu ra.

## Phụ thuộc / chuẩn bị

- Ngày 18

## Công việc

### Compose

- [x] Safe zone (~15% trên, ~20% dưới, mép phải), chữ nổi bật hook, karaoke `\k` tùy chọn.
- [x] Nhạc nền royalty-free, ducking `sidechaincompress`.
- [x] Xuất `final_review.mp4` và `final_review_voice_only.mp4`, `cover.jpg`.

### Đầu ra khác

- [x] `caption.txt` (mô tả + hashtag), `sources.md` (nguồn + trích dẫn theo cảnh), `project.json`.

### Web

- [x] Màn kết quả: xem trước video, tải từng file.

## Đầu ra

- Bộ đầu ra đầy đủ như mục 1 của plan

## Tiêu chí hoàn thành

- [x] Video đạt chuẩn đăng: 720×1280, h264+aac, thời lượng khớp tiếng ≤ 50ms, chữ trong safe zone (test tự động)

## Ghi chú kết quả

- Bản FFmpeg trên Mac không có libass/drawtext nên chữ (phụ đề, hook, karaoke) vẽ bằng Pillow thành chuỗi PNG rồi overlay; `.ass` (có `\k`) vẫn xuất ra.
- Safe zone: trên 15%, dưới 20%, phải 12%. Hook hiện 5 giây đầu, chữ trên màn hình của cảnh khác 3 giây đầu cảnh. Karaoke bật bằng `options.karaoke`.
- Nhạc nền tự tổng hợp bằng ffmpeg (hợp âm ambient, không vướng bản quyền), ducking `sidechaincompress`. Bản voice-only không nhạc để gắn nhạc trong app.
- Đầu ra: `final_review.mp4`, `final_review_voice_only.mp4`, `cover.jpg`, `caption.txt`, `sources.md`, `project.json`, `subtitles.srt/.ass`. API `GET /projects/{id}/outputs` (+ `/{key}`), web có màn Kết quả.
- Chưa làm: tự xem thử trên điện thoại thật; số ảnh cảnh vẫn 11–13/sách (xem ghi chú ngày 18).

---

[← Ngày 18](day-18.md) · [Mục lục](README.md) · [Ngày 20 →](day-20.md)
