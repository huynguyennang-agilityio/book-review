# Spike media (Ngày 1)

Code thử nghiệm, không dùng trong sản phẩm. Kết quả và quyết định nằm ở [docs/spikes/day-01-media.md](../../docs/spikes/day-01-media.md) và [ADR 0001](../../docs/decisions/0001-ken-burns-scale-crop.md).

Thư mục `out/` chứa output khi chạy, đã được gitignore.

## Chuẩn bị

- FFmpeg có `libass` (`ffmpeg -filters | grep subtitles`)
- Python 3.11+ với `numpy`, `pillow` (cho jitter check)
- `pip install edge-tts fal-client` (chỉ cho bước TTS và Fal)
- `FAL_KEY` trong môi trường (chỉ cho bước Fal)

## Chạy

| Việc | Lệnh | Cần mạng/key |
| --- | --- | --- |
| Ken Burns A/B | `bash kenburns_test.sh` | Không |
| Đo rung | `python jitter_check.py out/kenburns/A_zoompan.mp4` | Không |
| Burn phụ đề | `bash subtitle_burn_test.sh` | Không (cần bước Ken Burns A trước) |
| WordBoundary edge-tts | `python tts_wordboundary.py samples/*.txt` | Có, tới speech.platform.bing.com |
| So sánh model ảnh | `python fal_compare.py --ref ref/character.jpg` | Có, `FAL_KEY` |

`fal_compare.py` cần một ảnh nhân vật tham chiếu tại `ref/character.jpg` (không đưa vào repo). Tên endpoint Fal cần kiểm tra lại trước khi chạy.

## File

- `kenburns_test.sh`: hai cách Ken Burns, zoompan (A) và scale+crop (B)
- `jitter_check.py`: đo độ đều của dịch chuyển ngang giữa các frame
- `subtitle_test.ass`, `subtitle_burn_test.sh`: kiểm tra dấu tiếng Việt khi burn
- `tts_wordboundary.py`, `samples/`: đo WordBoundary cho 2 giọng vi-VN, báo từ mất và drift thời lượng
- `fal_compare.py`: so sánh 3 model chỉnh ảnh tham chiếu, xuất bảng chấm
