# Ngày 15: Frontend: duyệt kịch bản, hủy job

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Duyệt và sửa kịch bản ngay trên web, graph chạy tiếp sau khi duyệt, hủy được giữa chừng.

## Phụ thuộc / chuẩn bị

- Ngày 14

## Công việc

### Màn duyệt kịch bản

- [ ] Generative UI cho interrupt `review_script` (`renderAndWaitForResponse`).
- [ ] Kịch bản bên trái, nguồn trích dẫn của cảnh đang chọn bên phải, câu không có nguồn được tô màu.
- [ ] Hiện điểm faithfulness, cờ `LOW_FAITHFULNESS`, chi phí ước tính.
- [ ] Sửa trực tiếp từng cảnh, hoặc yêu cầu viết lại một cảnh bằng lời. Nút Duyệt.

### Hủy

- [ ] `POST /projects/{id}/cancel` đặt cờ, node và worker dừng, chi phí đã tiêu vẫn được ghi, trạng thái `cancelled`.
- [ ] Nút Hủy trên UI, hiển thị lỗi theo mã lỗi.

## Đầu ra

- Màn duyệt kịch bản hoàn chỉnh
- Test hủy giữa chừng

## Tiêu chí hoàn thành

- [ ] Duyệt kịch bản trên web rồi graph chạy tiếp
- [ ] Hủy giữa chừng được

## Ghi chú

- Không cho phép bất kỳ bước tạo ảnh/video tốn tiền nào chạy trước khi duyệt kịch bản.

---

[← Ngày 14](day-14.md) · [Mục lục](README.md) · [Ngày 16 →](day-16.md)
