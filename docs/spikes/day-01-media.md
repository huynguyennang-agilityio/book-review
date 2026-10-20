# Spike Ngày 1: media

> Kết quả thử nghiệm cho [Ngày 1](../plan/day-01.md). Code thử nằm ở `spikes/media/`.

## Trạng thái

| Hạng mục | Trạng thái | Ghi chú |
| --- | --- | --- |
| Ken Burns không rung | ✅ Đã đo | Scale 2× + crop theo thời gian mượt hơn zoompan thuần (bảng dưới) |
| Phụ đề tiếng Việt burn bằng libass | ✅ Đã kiểm tra | Dấu hiển thị đúng với DejaVu Sans; font sản phẩm chưa chọn |
| Word timing edge-tts (WordBoundary) | ⏳ Chưa chạy | Môi trường cloud không resolve được `speech.platform.bing.com` |
| Forced alignment (whisperX / stable-ts) | ⏳ Chưa chạy | Chưa cài; cần mẫu audio từ bước trên |
| So sánh model ảnh tham chiếu trên Fal | ⏳ Chưa chạy | Cần `FAL_KEY`; môi trường cloud bị chặn `queue.fal.run` |

Hai mục ⏳ cần chạy trên máy có mạng và có API key. Hướng dẫn chạy nằm ở [spikes/media/README.md](../../spikes/media/README.md).

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

## 3. Word timing (chưa có số liệu)

Việc cần làm trên máy có mạng:

1. `pip install edge-tts`, chạy `python spikes/media/tts_wordboundary.py spikes/media/samples/*.txt`.
2. Đọc `spikes/media/out/tts/summary.json`: số từ mất (`words_missing`) và `drift_ms` (thời lượng ffprobe trừ offset cuối).
3. Nếu WordBoundary thiếu từ có dấu hoặc drift vượt vài trăm ms, dùng forced alignment làm nguồn chính (theo ghi chú trong [Ngày 1](../plan/day-01.md)).

## 4. Model ảnh tham chiếu (chưa có số liệu)

Script `spikes/media/fal_compare.py` chạy 3 model (FLUX.1 Kontext, Qwen-Image-Edit, Seedream v4 edit) với cùng ảnh nhân vật và 4 prompt cảnh, rồi ghi `out/fal/scores.csv` để chấm tay.

Bảng chấm (điền sau khi chạy):

| Model | Giống nhân vật (1–5) | Đúng 9:16 | Lỗi | Thời gian (s) | Giá / ảnh | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| FLUX.1 Kontext | | | | | | |
| Qwen-Image-Edit | | | | | | |
| Seedream v4 edit | | | | | | |

ID endpoint và tên tham số trên Fal cần kiểm tra lại trước khi chạy.
