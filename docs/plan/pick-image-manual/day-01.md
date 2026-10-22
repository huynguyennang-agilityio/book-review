# Ngày 1: Ô tác giả (không bắt buộc)

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Thêm nhập tác giả để research và xác nhận sách chính xác hơn.

## Phụ thuộc / chuẩn bị

- Ngày 14 (form nhập sách)
- Ngày 9 (xác nhận sách)

## Công việc

- [ ] **Web**: `BookForm.tsx`: ô "Tác giả (không bắt buộc)", cắt khoảng trắng, tối đa ~100 ký tự, rỗng thì gửi `null`; `run.ts` gửi `book.author`.
- [ ] **Backend**: `precheck`/`projects.py`: làm sạch và giới hạn độ dài `author` như `title`.
- [ ] **Research**: Đưa tác giả vào truy vấn tìm kiếm (`"<tên sách>" <tác giả>`), `identify_confirm` ưu tiên ứng viên khớp tác giả và cảnh báo nếu không khớp; khoá cache/RAG của sách gồm cả tác giả.
- [ ] **Test**: Có/không tác giả, hai sách trùng tên khác tác giả, tác giả sai hiện cảnh báo. Series vẫn là trường riêng.

## Tiêu chí hoàn thành

- [ ] Nhập tên + tác giả cho ra đúng sách; không nhập tác giả thì hành vi như cũ

---

[Mục lục](README.md) · [Ngày 2 →](day-02.md)
