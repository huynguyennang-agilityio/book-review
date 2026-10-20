# ADR 0001: Ken Burns bằng phóng 2× rồi crop theo thời gian

- Trạng thái: Chấp nhận
- Ngày: 2026-10-20
- Liên quan: [Ngày 1 — spike media](../plan/day-01.md), [kết quả spike](../spikes/day-01-media.md)

## Bối cảnh

Video review cần Ken Burns trên ảnh 9:16 (720×1280@30fps). `zoompan` là cách phổ biến nhất trong FFmpeg, nhưng khi thử trượt ngang đều thì chuyển động bị giật: một số frame bị lặp (dịch chuyển 0) rồi nhảy khoảng 3.5 px.

## Quyết định

Dùng `scale` lên 2× rồi `crop` với biểu thức theo frame (`n`), sau đó `scale` xuống 720×1280:

```
scale=2160:3840,crop=w=1728:h=3072:x='(iw-1728)*n/149':y='(ih-3072)/2',scale=720:1280,setsar=1
```

## Lý do

Đo trên clip 150 frame, trượt ngang đều (`spikes/media/jitter_check.py`):

| Cách | Std dịch chuyển/frame |
| --- | --- |
| `zoompan` thuần | 0.794 px |
| Scale 2× + crop + scale xuống | 0.075 px |

Phương án B mượt hơn khoảng 10 lần. Phép scale xuống sau crop làm mịn phần làm tròn toạ độ.

## Hệ quả

- Tốn CPU hơn zoompan (scale ảnh lên 2160×3840 trước khi crop). Chấp nhận được vì mỗi cảnh chỉ vài giây.
- Chỉ đo trên pan ngang. Zoom và pan chéo chưa đo; khi làm ngày 13 cần kiểm tra lại bằng mắt trên ít nhất một cảnh.
- Phase 2 dùng I2V cho hook và vài cảnh; Ken Burns vẫn là phương án dự phòng khi I2V lỗi.
