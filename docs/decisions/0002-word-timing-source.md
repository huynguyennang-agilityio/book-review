# ADR 0002: Word timing lấy từ WordBoundary của edge-tts

- Trạng thái: Chấp nhận
- Ngày: 2026-10-20
- Liên quan: [Ngày 1 — spike media](../plan/day-01.md), [kết quả spike](../spikes/day-01-media.md)

## Bối cảnh

Phụ đề từng từ và timeline tuyệt đối cần thời điểm bắt đầu của mỗi từ. Hai nguồn khả dĩ: `WordBoundary` do edge-tts trả cùng audio, hoặc forced alignment (stable-ts / whisperX) chạy sau.

## Quyết định

Dùng `WordBoundary` (`vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`) làm nguồn chính. Giữ stable-ts làm phương án dự phòng cho nhà cung cấp TTS không trả timestamp. Độ dài clip lấy từ `ffprobe`, không tính từ offset từ cuối.

## Lý do

Đo trên 3 đoạn mẫu × 2 giọng (17–20 giây mỗi đoạn):

- WordBoundary trả đủ 206/206 từ, kể cả từ có dấu.
- Thời lượng ffprobe dài hơn thời điểm kết thúc từ cuối khoảng 840 ms ở mọi mẫu. Đó là khoảng lặng cuối file edge-tts chèn, không phải lệch tích luỹ. Từ đầu tiên bắt đầu ở 100–137 ms.
- stable-ts (model `base`) lệch so với WordBoundary trung bình 39–60 ms, tối đa 285 ms, tức khoảng 1–2 frame ở 30 fps.

## Hệ quả

- Không cần cài torch hay model Whisper trong worker ở bản đầu.
- Khi ghép cảnh cần dùng ffprobe để lấy độ dài và có thể cắt khoảng 0,8 s đuôi lặng.
- Chưa nghe bằng tai để biết nguồn nào chuẩn hơn, và các mẫu ngắn hơn mốc 30 giây trong kế hoạch. Cần kiểm tra lại trên một đoạn dài khi làm timeline ở ngày 12.
- `edge-tts` không có cam kết dịch vụ; nếu ngừng hoạt động thì đổi `TTSProvider` và dùng stable-ts.
