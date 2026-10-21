# Ngày 12: Walking skeleton media: worker, TTS, timeline

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Render worker nhận job qua hàng đợi, tạo giọng đọc và timeline tuyệt đối cho toàn bộ video.

## Phụ thuộc / chuẩn bị

- Ngày 1 (cách lấy word timing)
- Ngày 11 (storyboard đã duyệt)

## Công việc

### Worker

- [x] `apps/worker`: arq + Redis, `WorkerSettings`, job `tts`, `images`, `motion`, `compose` (stub cho phần chưa làm).
- [x] API đẩy job, worker cập nhật tiến độ, graph chờ kết quả.

### TTS

- [x] `providers/tts_edge.py`: `TTSProvider` interface, edge-tts với `Semaphore(2)`, WordBoundary.
- [x] `providers/aligner.py`: forced alignment dự phòng.

### Timeline

- [x] `media/timeline.py`: tính `start/end` tuyệt đối cho từng cảnh và shot, nghỉ 0.15–0.3s giữa cảnh, lưu vào state.
- [x] Unit test timeline: tổng thời lượng, không chồng lấn, shot 3–6s.

## Đầu ra

- Worker chạy trong docker-compose
- Node `tts_align` và `build_timeline`

## Ghi chú khi làm

- `providers/` của TTS nằm trong `apps/worker` (worker mới chạy TTS), không phải `apps/api`.
- Thêm job `timeline` để API không phải import code media. Đường dẫn audio trong state tương đối so với `MEDIA_DIR`, vì API và container worker gắn thư mục media ở chỗ khác nhau.
- Chạy thật `scripts/run_media.py` trên 3 đoạn mẫu: 3 cảnh, tổng 54,7 s, mỗi cảnh 4 shot 4,3–4,8 s.

## Tiêu chí hoàn thành

- [x] Từ storyboard tạo được audio và timeline tuyệt đối, test timeline xanh

---

[← Ngày 11](day-11.md) · [Mục lục](README.md) · [Ngày 13 →](day-13.md)
