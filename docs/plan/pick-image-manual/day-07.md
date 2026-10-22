# Ngày 7: Chạy thật, hoàn thiện, tài liệu

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Chạy cả hai chế độ, sửa lỗi, cập nhật tài liệu.

## Phụ thuộc / chuẩn bị

- Ngày 1–6 của bộ này

## Công việc

> Kết quả chạy thật: Nhà giả kim, 23 ảnh cảnh + 2 nhân vật từ ảnh mẫu, 0 USD tiền ảnh, video 91s 720×1280 h264+aac. Gemini viết ~17–18 cảnh (~90–100s) kể cả khi đặt 5 phút, đây là độ dài kịch bản chứ không phải của manual. 24 cảnh cho ≤ 35 ảnh; trần 35 giữ, chỉ vượt khi > 35 cảnh nên chưa cần nâng. Hai nhánh song song: graph đầy đủ ở `tests/unit/test_manual_images.py` đã chạy qua `motion`, không lỗi nên không phải xếp tuần tự. Lỗi sửa: trang tải ảnh web bị gỡ khi chạy lại (pending bị xoá) nên mất ô đã tải; nay giữ bản nháp ở `useReviewRun`. Bộ nhớ sở thích lưu auto/manual: không làm (tuỳ chọn).

- [x] **Chạy thật**: Script `scripts/run_scene_images.py --manual-dir` nạp ảnh từ thư mục; `run_media.py` dựng video 3 phút (~24 cảnh) từ ảnh manual.
- [x] **Kiểm tra số ảnh**: Kiểm tra `scene_images_max=35` khi video dài hơn 3 phút; ghi nhận nếu cần nâng.
- [x] **Sửa lỗi**: Hai nhánh cùng `interrupt` song song; nếu lỗi thì xếp tuần tự.
- [x] **Tài liệu**: Cập nhật README và `docs/project-plan-v5.md` nếu cần; cập nhật bộ nhớ sở thích (tuỳ chọn) lưu lựa chọn auto/manual.

## Tiêu chí hoàn thành

- [x] Video 3 phút từ ảnh manual đạt chuẩn như auto; test, ruff, mypy xanh

---

[← Ngày 6](day-06.md) · [Mục lục](README.md)
