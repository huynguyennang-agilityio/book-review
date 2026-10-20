#!/usr/bin/env bash
# Spike Ngày 1: burn file .ass tiếng Việt lên video 720x1280 bằng libass.
# Chạy sau kenburns_test.sh (dùng clip A làm nền):
#   bash spikes/media/subtitle_burn_test.sh
# Font: thử với DejaVu Sans (có đủ glyph tiếng Việt). Trên máy khác, đổi FONTSDIR tới thư mục chứa font đã chọn.
set -euo pipefail

cd "$(dirname "$0")"
OUT="${OUT:-out/subtitle}"
mkdir -p "$OUT"
FONTSDIR="${FONTSDIR:-/usr/share/fonts/truetype/dejavu}"
BG="${BG:-out/kenburns/A_zoompan.mp4}"

ffmpeg -y -loglevel error -i "$BG" -t 5 \
  -vf "subtitles=subtitle_test.ass:fontsdir=${FONTSDIR}" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a none "$OUT/burned.mp4"

# Lấy 2 frame để xem bằng mắt: 1s (dòng đầu) và 3.5s (dòng thứ hai).
ffmpeg -y -loglevel error -ss 1 -i "$OUT/burned.mp4" -frames:v 1 "$OUT/frame_1s.png"
ffmpeg -y -loglevel error -ss 3.5 -i "$OUT/burned.mp4" -frames:v 1 "$OUT/frame_3_5s.png"
echo "Đã xuất: $OUT/burned.mp4, $OUT/frame_1s.png, $OUT/frame_3_5s.png"
