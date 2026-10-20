# ADR 0003: Model ảnh nhân vật là Seedream v4 edit, dự phòng Qwen-Image-Edit

- Trạng thái: Chấp nhận (sơ bộ, kiểm tra lại ở ngày 16–18)
- Ngày: 2026-10-20
- Liên quan: [Ngày 1 — spike media](../plan/day-01.md), [kết quả spike](../spikes/day-01-media.md)

## Bối cảnh

Video cần cùng một nhân vật xuất hiện qua nhiều cảnh. Cần chọn model chỉnh ảnh theo tham chiếu trên Fal.

## Quyết định

Dùng Seedream v4 edit (`fal-ai/bytedance/seedream/v4/edit`) làm model chính. Dùng Qwen-Image-Edit làm phương án dự phòng rẻ hơn.

## Lý do

Chạy 3 model × 4 cảnh với 1 ảnh tham chiếu, chấm bằng mắt (chỉ mang tính định hướng):

| Model | Giống nhân vật | Ảnh ra | Giá / ảnh |
| --- | --- | --- | --- |
| Seedream v4 edit | 4/5 | 1080×1920, đúng 9:16 | 0,03 USD |
| Qwen-Image-Edit | 4/5 | 720×1280, đúng 9:16 | ~0,028 USD |
| FLUX.1 Kontext | 3/5 | 752×1392, không đúng 9:16 | 0,04 USD |

Seedream giữ mặt và độ tuổi tốt nhất, tư thế tự nhiên theo từng cảnh, độ phân giải cao nhất. Qwen rẻ nhất nhưng lặp tư thế của ảnh gốc ở cả 4 cảnh. FLUX làm mặt già hơn và đổi áo, hành động giữa các cảnh.

## Hệ quả

- Ảnh tham chiếu phải sạch: không watermark, nền trung tính, tư thế đứng thẳng. Cả 3 model đều chép nền hoặc watermark khi cảnh gần giống ảnh gốc.
- Mỗi model chỉ có 4 ảnh và 1 ảnh tham chiếu. Ở ngày 16–18 cần chạy lại với sheet nhân vật nhiều góc và nhiều cảnh hơn trước khi chốt mốc nhận ra nhân vật ở ≥ 80% cảnh.
- Tên endpoint và tham số kích thước (`image_size`, không phải `aspect_ratio`) cần kiểm tra lại khi Fal đổi API.
