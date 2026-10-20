#!/usr/bin/env bash
# Spike Ngày 1: hai cách Ken Burns, xuất 720x1280@30fps, 5 giây.
#   A: zoompan thuần
#   B: phóng 2x rồi crop theo biểu thức thời gian, cuối cùng scale xuống 720x1280
#
# Chạy: bash spikes/media/kenburns_test.sh [ảnh_nguồn]
# Không truyền ảnh thì tự sinh ảnh test 1080x1920.
# Sau đó chạy: python spikes/media/jitter_check.py out/kenburns/A_zoompan.mp4 (và B)
set -euo pipefail

cd "$(dirname "$0")"
OUT="${OUT:-out/kenburns}"
mkdir -p "$OUT"

SRC="${1:-}"
if [ -z "$SRC" ]; then
  SRC="$OUT/source_1080x1920.png"
  ffmpeg -y -loglevel error -f lavfi -i "testsrc2=size=1080x1920:rate=1" -frames:v 1 "$SRC"
fi

DUR=5
FPS=30
LAST=$((DUR * FPS - 1))   # 149
ZOOM=1.25

# A: zoompan thuần. Zoom cố định, trượt ngang tuyến tính theo 'on' (số thứ tự frame).
ffmpeg -y -loglevel error -loop 1 -framerate $FPS -t $DUR -i "$SRC" \
  -vf "zoompan=z=${ZOOM}:x='(iw-iw/zoom)*on/${LAST}':y='(ih-ih/zoom)/2':d=1:s=720x1280:fps=${FPS}" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 "$OUT/A_zoompan.mp4"

# B: phóng 2x, crop cửa sổ 1728x3072 (zoom 1.25) trượt theo n, rồi scale xuống 720x1280.
# eval=frame để biểu thức được tính lại mỗi frame.
ffmpeg -y -loglevel error -loop 1 -framerate $FPS -t $DUR -i "$SRC" \
  -vf "scale=2160:3840,crop=w=1728:h=3072:x='(iw-1728)*n/${LAST}':y='(ih-3072)/2',scale=720:1280,setsar=1" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 "$OUT/B_upscale_crop.mp4"

echo "Đã xuất: $OUT/A_zoompan.mp4, $OUT/B_upscale_crop.mp4"
