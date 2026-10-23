# Tăng ngân sách và nạp tiền Fal rồi chạy lại project lỗi

Nguồn: [plan trên claude.ai](https://claude.ai/artifact/6PvdaxxHAkrBBzAxzGxmuf).

## Vấn đề

- Project dừng vì `BUDGET_EXCEEDED` thì chạy lại vẫn dùng ngân sách cũ (`options.budget_usd`), nên dừng đúng chỗ cũ.
- Tua lại checkpoint làm mất khỏi `cost` phần tiền đã trả trong lần lỗi.
- Fal hết tiền hoặc 429 bị coi như ảnh bị bộ lọc chặn: ghi `.blocked`, đổi sang bản ẩn dụ, mượn ảnh khác, video vẫn ra với ảnh lặp.

## Cách làm

- Web gửi `forwardedProps.budget_usd` khi bấm "Thử lại". API (`agui._rewind_failed`) ghi `options.budget_usd` mới và phần chênh lệch `cost` của lần lỗi vào checkpoint cần tua. `__copy__` bỏ qua giá trị nên phải ghi thay một node trong `parent.next`; chỉ nhận lần ghi mà các node chờ chạy không đổi.
- Ngân sách mới phải là số, lớn hơn số đã tiêu, không quá `max_budget_usd` (mặc định 20). Sai thì 422 `VALIDATION_ERROR`.
- Lỗi tài khoản Fal (401, 402, 403, 429) thành `ImageAccountError`; `character_sheets` và `scene_images` dừng hẳn với `PROVIDER_QUOTA`, không ghi `.blocked`, không mượn ảnh. Nạp tiền xong bấm "Thử lại" chạy tiếp; ảnh đã tạo có cache nên không tính tiền lại.

## Các bước

| Bước | Nội dung |
| --- | --- |
| 1 | API nhận ngân sách mới khi chạy lại, giữ chi phí lần lỗi |
| 2 | Lỗi tài khoản Fal dừng hẳn với `PROVIDER_QUOTA` |
| 3 | Web: ô "Ngân sách mới" khi lỗi `BUDGET_EXCEEDED`, câu báo cho `PROVIDER_QUOTA` |
| 4 | Chạy nốt project bị `BUDGET_EXCEEDED` ngày 23/10 |

File `.blocked` ghi nhầm vì lỗi tài khoản trước bước 2 không tự xoá được (không phân biệt với ảnh bị bộ lọc chặn thật); xoá tay trong `var/media/images/scenes` nếu biết thời điểm hết tiền.
