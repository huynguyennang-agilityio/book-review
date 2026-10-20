# Ngày 1: Spike media

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Trả lời bằng thử nghiệm thật 4 câu hỏi media trước khi viết code sản phẩm: lấy word timing thế nào, dùng model ảnh tham chiếu nào, làm Ken Burns ra sao, và burn phụ đề tiếng Việt có đúng font không.

## Phụ thuộc / chuẩn bị

- Tài khoản Fal.ai có API key
- FFmpeg build có `libass` trên máy
- Thư mục `spikes/` (không đưa vào code sản phẩm)

## Công việc

### Sáng: TTS và word timing

- [ ] Chạy `edge-tts` với `vi-VN-HoaiMyNeural` và `vi-VN-NamMinhNeural`, bật `boundary="WordBoundary"`, lưu mp3 + danh sách từ kèm offset.
- [ ] Kiểm tra WordBoundary có trả đủ từ tiếng Việt có dấu không, đo độ lệch so với nghe thực tế trên 3 đoạn 30 giây.
- [ ] Chạy `whisperX` (hoặc `stable-ts`) forced alignment trên cùng audio, so sánh timing với WordBoundary.
- [ ] Đo thời lượng bằng `ffprobe`, so với tổng offset từ WordBoundary.

### Chiều: ảnh và motion

- [ ] Viết script gọi 2–3 model ảnh tham chiếu trên Fal (FLUX.1 Kontext, Qwen-Image-Edit, Seedream hoặc Gemini image) với cùng 1 ảnh nhân vật + 4 prompt cảnh.
- [ ] Chấm nhanh: độ giống nhân vật, chất lượng 9:16, thời gian, giá mỗi ảnh. Ghi vào bảng so sánh.
- [ ] Thử 2 cách Ken Burns: `zoompan` thuần và scale lên 2× rồi `crop` theo biểu thức thời gian. Xuất 720×1280@30fps, xem có rung (jitter) không.
- [ ] Burn thử file `.ass` có tiếng Việt qua `subtitles=...:fontsdir=fonts/`, kiểm tra dấu (ạ, ỗ, ữ) hiển thị đúng.

## Đầu ra

- `docs/spikes/day-01-media.md`: bảng so sánh model ảnh, timing, ảnh chụp kết quả
- Script spike trong `spikes/media/`
- Quyết định đã chốt ghi vào `docs/decisions/` (ADR ngắn)

## Tiêu chí hoàn thành

- [ ] Đã chốt model ảnh tham chiếu (ghi lý do và giá)
- [ ] Đã chốt cách Ken Burns không rung
- [ ] Đã chốt nguồn word timing chính và phương án dự phòng
- [ ] Burn phụ đề tiếng Việt hiển thị đúng dấu

## Ghi chú

- Không tối ưu code spike, mục tiêu là quyết định.
- Nếu WordBoundary thiếu từ, mặc định dùng forced alignment làm nguồn chính.

---

[Mục lục](README.md) · [Ngày 2 →](day-02.md)
