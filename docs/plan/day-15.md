# Ngày 15: Frontend: duyệt kịch bản, hủy job

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Duyệt và sửa kịch bản ngay trên web, graph chạy tiếp sau khi duyệt, hủy được giữa chừng.

## Phụ thuộc / chuẩn bị

- Ngày 14

## Công việc

### Màn duyệt kịch bản

- [x] Generative UI cho interrupt `review_script` (`renderAndWaitForResponse`).
- [x] Kịch bản bên trái, nguồn trích dẫn của cảnh đang chọn bên phải, câu không có nguồn được tô màu.
- [x] Hiện điểm faithfulness, cờ `LOW_FAITHFULNESS`, chi phí ước tính.
- [x] Sửa trực tiếp từng cảnh, hoặc yêu cầu viết lại một cảnh bằng lời. Nút Duyệt.

### Hủy

- [x] `POST /projects/{id}/cancel` đặt cờ, node và worker dừng, chi phí đã tiêu vẫn được ghi, trạng thái `cancelled`.
- [x] Nút Hủy trên UI, hiển thị lỗi theo mã lỗi.

## Đầu ra

- Màn duyệt kịch bản hoàn chỉnh
- Test hủy giữa chừng

## Tiêu chí hoàn thành

- [x] Duyệt kịch bản trên web rồi graph chạy tiếp
- [x] Hủy giữa chừng được

## Ghi chú

- Màn duyệt (`apps/web/app/_components/ScriptReview.tsx`) đọc payload interrupt `review_script`: kịch bản bên trái, nguồn trích dẫn và ý chưa có căn cứ của cảnh đang chọn bên phải. Câu bị tô màu là câu mà giám khảo faithfulness đánh dấu chưa có căn cứ (lưu ở `scene.unsupported`) hoặc cảnh `context`/`body` không có trích dẫn nào. Sửa tay xong thì điểm cũ không còn đúng nên bỏ tô màu.
- Resume `review_script`: `{"approved": true, "edits": [{"scene_id", "narration_vi", "on_screen_text_vi"}]}`. Cảnh sửa tay mất điểm, mất cờ `LOW_FAITHFULNESS`, mang cờ `EDITED`. Edits không hợp lệ (cảnh không có, lời đọc trống) thì project `failed` với `VALIDATION_ERROR` trước khi tốn tiền media.
- Viết lại một cảnh bằng lời: `POST /projects/{id}/scenes/{scene_id}/rewrite` `{instruction, narration_vi?}` chỉ trả bản đề xuất kèm điểm bám nguồn mới; kịch bản chỉ đổi khi bấm Duyệt kèm bản sửa.
- Huỷ: `POST /projects/{id}/cancel` (idempotent). Đặt cờ `br:cancel:<thread_id>` ở Redis: graph kiểm cờ trước mỗi node (không chạy node nữa, ghi `cancelled`), `ArqJobRunner` kiểm cờ khi chờ job và huỷ job đang chạy ở worker (`allow_abort_jobs`). Graph đang chờ duyệt thì ghi luôn `cancelled` vào state. Chi phí đã tiêu nằm trong `state.cost`, trả về trong response. Project `cancelled` không chạy lại được (`/agent` trả 409 `CANCELLED`); project đã `done`/`failed` trả 409 `INVALID_STATE`.
- `/agent` thật từ ngày 15 chạy cả storyboard, faithfulness và media qua worker (arq). Sau `review_script` graph dừng ở `review_characters` (làm ở ngày 17); web có nút "Tiếp tục với ảnh tạm" để dựng video bằng ảnh placeholder.
- Không cho phép bất kỳ bước tạo ảnh/video tốn tiền nào chạy trước khi duyệt kịch bản.

---

[← Ngày 14](day-14.md) · [Mục lục](README.md) · [Ngày 16 →](day-16.md)
