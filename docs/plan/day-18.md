# Ngày 18: Ảnh cảnh thật, tái dùng ảnh, fallback an toàn

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Thay ảnh placeholder bằng ảnh cảnh thật, nhân vật nhất quán, không bị kẹt khi ảnh bị bộ lọc chặn.

## Phụ thuộc / chuẩn bị

- Ngày 17

## Công việc

### Node `scene_images`

- [x] Số ảnh theo `image_plan`: trần 35, mỗi ảnh dùng cho 1–2 shot (`Shot.image_ref`). Storyboard hiện chỉ ~20 shot nên ra 11–13 ảnh, chưa đạt sàn 25 (xem ghi chú dưới).
- [x] Tạo theo tỷ lệ gần 9:16 (bội số 16) rồi crop chính xác 720×1280.
- [x] Tối đa 2 nhân vật mỗi khung, truyền ảnh tham chiếu đã duyệt.
- [x] Ảnh bị bộ lọc chặn thì đổi sang cảnh `metaphor` và tạo lại.
- [x] Cache theo hash prompt + seed, chạy lại không tạo lại ảnh đã có.

### Kiểm tra

- [x] Chạy 2 sách (Nhà giả kim, Hoàng tử bé) bằng `scripts/run_scene_images.py`, chấm tay trên contact sheet.

## Đầu ra

- Video có ảnh thật của 2 sách mẫu

## Tiêu chí hoàn thành

- [x] Nhân vật nhận ra được ở ≥ 80% cảnh: 13/13 ảnh có nhân vật đều nhận ra (Hoàng tử bé 8/8, Nhà giả kim 5/5)

## Ghi chú kết quả

- Video có ảnh thật chạy thử bằng sheet đầu tiên làm bản đã duyệt, chi phí ~1,2 USD cho 2 sách (ảnh cảnh 0,03 USD/ảnh).
- Số ảnh bị chặn bởi số shot: storyboard ra ~1,5–2 phút lời đọc nên chỉ 11–13 ảnh. Muốn 25–35 ảnh cần kịch bản dài ~3 phút (`storyboard_minutes`) hoặc nhiều shot ngắn hơn.
- Prompt ảnh do model viết một lần cho cả storyboard (`storyboard/images.py`), lỗi thì dùng prompt mặc định.

---

[← Ngày 17](day-17.md) · [Mục lục](README.md) · [Ngày 19 →](day-19.md)
