# Ảnh cảnh bị xoay ngang 90°

Nguồn: [plan trên claude.ai](https://claude.ai/artifact/7FHpCicDXULAG95WSRCs3T).

## Nguyên nhân (đo 24/10, project "Kiêu hãnh và Định kiến")

- 5/35 ảnh cảnh bị vẽ nằm ngang, cả 5 là `seedream/v4/text-to-image` (5/21 ảnh không có tham chiếu; 0/14 ảnh `edit` có tham chiếu).
- Ảnh gốc Fal trả về 1088×1920, không có thẻ EXIF xoay: chính model vẽ cảnh nằm ngang. Prompt ảnh xoay và ảnh đúng gần như giống nhau.

## Cách làm

- `storyboard/orientation.py`: thu ảnh về 360×640, hỏi Gemini (`judge_model`) `upright | rotated | unsure`; lỗi model là `unsure`. Đo trên 35 ảnh trên: bắt 5/5, báo nhầm 0/30, ~1.220 token/ảnh.
- `scene_images`: ảnh mới bị xoay thì tạo lại một lần với `seed + 1` (nếu còn ngân sách), ghi vào khoá cache của seed gốc. Xoay hai lần thì sang cảnh ẩn dụ, không ghi `.blocked`. Hết ngân sách thì giữ ảnh xoay và ghi log. Ảnh xoay không vào cache. `cost.rotated_images` đếm số ảnh xoay.
- Tắt bằng `SCENE_ORIENTATION_CHECK=false`.

## Các bước

| Bước | Nội dung | PR |
| --- | --- | --- |
| 1 | Chi phí cần giữ khi chạy lại lấy từ state lỗi mới nhất | #68 |
| 2 | Bộ kiểm tra hướng ảnh + đo | #69 |
| 3 | Tạo lại ảnh xoay trong `scene_images` | PR này |
| 4 | Sửa video 23/10 (xoá cache ảnh xoay, chạy lại từ `scene_images`) | không cần PR |
