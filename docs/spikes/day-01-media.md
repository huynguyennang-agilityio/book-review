# Spike Ngày 1: media

> Kết quả thử nghiệm cho [Ngày 1](../plan/day-01.md). Code thử nằm ở `spikes/media/`.

## Trạng thái

| Hạng mục | Trạng thái | Ghi chú |
| --- | --- | --- |
| Ken Burns không rung | ✅ Đã đo | Scale 2× + crop theo thời gian mượt hơn zoompan thuần (bảng dưới) |
| Phụ đề tiếng Việt burn bằng libass | ✅ Đã kiểm tra | Dấu hiển thị đúng với DejaVu Sans; font sản phẩm chưa chọn |
| Word timing edge-tts (WordBoundary) | ✅ Đã đo | Đủ 206/206 từ trên 2 giọng; đuôi lặng cố định ~840 ms, không có drift |
| Forced alignment (whisperX / stable-ts) | ✅ Đã đo | stable-ts khớp WordBoundary, lệch start trung bình 39–60 ms |
| So sánh model ảnh tham chiếu trên Fal | ⏳ Chưa chạy | Đã có key và ảnh tham chiếu; tài khoản Fal hết số dư (403) |

Mục ⏳ cần nạp tiền vào tài khoản Fal rồi chạy lại. Hướng dẫn chạy nằm ở [spikes/media/README.md](../../spikes/media/README.md).

## 1. Ken Burns: zoompan thuần so với phóng 2× rồi crop

Đo trên clip 720×1280@30fps, 5 giây (150 frame), trượt ngang đều, zoom 1.25. Script: `spikes/media/jitter_check.py`.

| Cách | Dịch chuyển trung bình (px/frame) | Std (px) | Độ lệch lớn nhất (px) | Nhận xét |
| --- | --- | --- | --- | --- |
| A. `zoompan` thuần | +1.283 | 0.794 | 1.283 | Có frame lặp (dịch = 0) rồi nhảy khoảng 3.5 px, nhìn thấy rung |
| B. Scale 2× + `crop` theo `n` + scale xuống | +1.127 | 0.075 | 0.258 | Mượt |

Lưu ý: trung bình của A và B khác nhau vì zoompan làm tròn toạ độ theo cách khác. Tiêu chí ở đây là độ đều, không phải tốc độ.

Quyết định: dùng cách B. Chi tiết trong [ADR 0001](../decisions/0001-ken-burns-scale-crop.md).

## 2. Phụ đề tiếng Việt (libass)

- File thử: `spikes/media/subtitle_test.ass` (PlayRes 720×1280, căn giữa dưới, MarginV 448).
- Burn bằng `subtitles=...:fontsdir=/usr/share/fonts/truetype/dejavu`.
- Kết quả: dòng "Ạ Ỗ Ữ ấ ế ộ ự ậ" hiển thị đúng dấu, không bị thiếu glyph.
- Chưa làm: kiểm tra trên font khác (ví dụ Be Vietnam Pro, Inter) và bản đóng gói trong Docker image. Font thật sẽ chọn ở ngày 13 khi làm phụ đề.

## 3. Word timing: WordBoundary và forced alignment

Chạy ngày 2026-10-20 trên macOS (M1), edge-tts 7.3.1, 3 đoạn mẫu trong `spikes/media/samples/` (dài 17–20 giây, ngắn hơn mốc 30 giây trong kế hoạch). Script: `tts_wordboundary.py`, `align_compare.py`.

### WordBoundary

| Giọng | Mẫu | Từ trả về / từ gốc | Từ mất | ffprobe (ms) | Từ cuối kết thúc (ms) | `drift_ms` |
| --- | --- | --- | --- | --- | --- | --- |
| HoaiMy | sample_01 | 67 / 67 | 0 | 17640 | 16800 | 840 |
| HoaiMy | sample_02 | 67 / 67 | 0 | 18936 | 18100 | 836 |
| HoaiMy | sample_03 | 72 / 72 | 0 | 19752 | 18912 | 840 |
| NamMinh | sample_01 | 67 / 67 | 0 | 17256 | 16412 | 844 |
| NamMinh | sample_02 | 67 / 67 | 0 | 19056 | 18212 | 844 |
| NamMinh | sample_03 | 72 / 72 | 0 | 19896 | 19050 | 846 |

- Không mất từ nào, kể cả từ có dấu.
- `drift_ms` gần như không đổi (836–846 ms) dù độ dài file khác nhau, nên đây không phải lệch tích luỹ. `silencedetect` (−40 dB) trên HoaiMy/sample_01 cho thấy khoảng lặng bắt đầu ở 16 793 ms, trùng với lúc từ cuối kết thúc (16 800 ms): edge-tts chèn khoảng 840 ms lặng ở cuối file.
- Từ đầu tiên bắt đầu ở 100–137 ms (lặng đầu file).
- Hệ quả cho pipeline: dùng thời lượng ffprobe làm độ dài clip, và có thể cắt khoảng 0,8 s đuôi lặng khi ghép cảnh.

### Forced alignment (stable-ts, model whisper `base`)

So sánh thời điểm bắt đầu của từng từ giữa stable-ts và WordBoundary (mọi từ đều ghép được 1–1):

| Giọng | Mẫu | Lệch TB (ms) | P90 (ms) | Lớn nhất (ms) |
| --- | --- | --- | --- | --- |
| HoaiMy | sample_01 | 39 | 78 | 162 |
| HoaiMy | sample_02 | 40 | 85 | 182 |
| HoaiMy | sample_03 | 44 | 86 | 250 |
| NamMinh | sample_01 | 51 | 130 | 232 |
| NamMinh | sample_02 | 53 | 173 | 285 |
| NamMinh | sample_03 | 60 | 161 | 242 |

- Hai nguồn lệch nhau khoảng 1–2 frame ở 30 fps, đủ cho phụ đề từng từ. Chưa nghe bằng tai để biết nguồn nào chuẩn hơn; WordBoundary do chính bộ tổng hợp trả nên mặc định coi là chuẩn.
- stable-ts cài bằng `pip install stable-ts` (kéo theo torch, khoảng vài trăm MB, cộng model `base` 139 MB). Không thử whisperX.

### Quyết định

- Dùng WordBoundary làm nguồn word timing chính cho edge-tts. Không cần forced alignment ở bước này.
- Giữ stable-ts làm phương án dự phòng cho nhà cung cấp TTS không trả timestamp.

### Ghi chú môi trường

Máy chạy chưa có FFmpeg (brew phải build từ source, quá chậm), nên lần đo này dùng FFmpeg 7.1 đóng gói trong `imageio-ffmpeg` và một shim `ffprobe` đọc thời lượng qua PyAV. Shim nằm ngoài repo. Thời lượng mp3 vì thế là ước lượng của libav, cùng cách `ffprobe -show_entries format=duration` làm.

## 4. Model ảnh tham chiếu (chưa có số liệu)

Script `spikes/media/fal_compare.py` chạy 3 model (FLUX.1 Kontext, Qwen-Image-Edit, Seedream v4 edit) với cùng ảnh nhân vật và 4 prompt cảnh, rồi ghi `out/fal/scores.csv` để chấm tay.

Bảng chấm (điền sau khi chạy):

| Model | Giống nhân vật (1–5) | Đúng 9:16 | Lỗi | Thời gian (s) | Giá / ảnh | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| FLUX.1 Kontext | | | | | | |
| Qwen-Image-Edit | | | | | | |
| Seedream v4 edit | | | | | | |

Endpoint đã đối chiếu OpenAPI của Fal ngày 2026-10-20: cả 3 ID còn tồn tại. Kontext nhận `aspect_ratio: "9:16"`, còn Qwen-Image-Edit và Seedream v4 edit nhận `image_size` (Seedream cần tối thiểu 921 600 px), nên `fal_compare.py` đã sửa để gửi đúng tham số cho từng model.

Lần chạy ngày 2026-10-20 (ảnh tham chiếu 1170×2080, 9:16, đặt ở `spikes/media/ref/`, không đưa vào repo) dừng ngay ở bước upload: Fal trả 403 "User is locked. Reason: Exhausted balance" cho cả storage lẫn queue. Cần nạp tiền ở fal.ai/dashboard/billing rồi chạy lại.
