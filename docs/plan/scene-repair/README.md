# Sửa riêng cảnh trích sai thay vì bỏ

Nguồn: [plan trên claude.ai](https://claude.ai/artifact/HqBFhMUW6Ect65Xjegvtid), bổ sung cho [plan sửa lỗi trích dẫn](https://claude.ai/artifact/Vck5rvPhYP6vU32AnRDR2s).

## Vấn đề

Từ PR #57, `write_section` viết lại cả phần tối đa `storyboard_retries` lần. Hết lượt mà còn cảnh trích sai thì `salvage_scenes` bỏ cảnh đó, nên video mất một đoạn.

## Cách làm (đã chọn)

Ngay trước `salvage_scenes`, gọi model sửa riêng từng cảnh còn lỗi (`StoryboardWriter._repair_scene`), tối đa `storyboard_scene_repairs` lần (mặc định 2, đặt 0 để tắt):

- Model nhận các đoạn nguồn của phần, lời đọc cũ, lỗi của cảnh và các cảnh khác (để không lặp ý). Nó trả về một `SceneDraft`.
- Kết quả đi qua `_resolve` như lúc viết cả phần, nên vẫn giữ id cảnh cũ và cùng kiểm tra citation.
- Nguồn không có ý đó thì model viết cảnh khác cùng chủ đề.
- Sửa không được (vẫn sai hoặc model trả lỗi) thì `salvage_scenes` bỏ cảnh như trước.

Không đổi prompt `storyboard_v3`, schema, DB hay web.

## Các bước

| Bước | Nội dung | Trạng thái |
| --- | --- | --- |
| 1 | `_repair_scene`, setting, log, unit test | PR này |
| 2 | Đo trên Mac bằng `scripts/run_storyboard.py` (3–5 sách golden): số cảnh sửa được, số cảnh còn bị bỏ, chi phí thêm | chưa làm |
| 3 | Tuỳ chọn: sửa riêng ngay từ lượt viết lại đầu khi lỗi chỉ là trích dẫn | chỉ làm nếu bước 2 cho thấy cần |
