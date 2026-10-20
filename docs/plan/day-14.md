# Ngày 14: Frontend: đăng nhập, chat, tiến độ

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Người dùng đăng nhập trên web, nhập tên sách, xem agent research và tiến độ graph theo thời gian thực.

## Phụ thuộc / chuẩn bị

- Ngày 13
- Spike CopilotKit ngày 2

## Công việc

### Web

- [ ] Đăng nhập Supabase Auth, gửi JWT tới API và endpoint AG-UI.
- [ ] Màn chat: nhập tên sách và tùy chọn (độ dài, no_spoiler, giọng, ngân sách).
- [ ] Hiển thị danh sách nguồn hiện dần, nguồn đã đọc, nguồn dùng cho kịch bản.
- [ ] Màn chọn đúng sách khi `identify_confirm` interrupt.
- [ ] Thanh tiến độ theo node.

### API

- [ ] Endpoint `/agent` kiểm tra JWT, stream event tiến độ, tool call, state, interrupt.

## Đầu ra

- Luồng đăng nhập → nhập sách → xem research chạy được trên web

## Tiêu chí hoàn thành

- [ ] Từ web khởi động được một project và thấy tiến độ thật

---

[← Ngày 13](day-13.md) · [Mục lục](README.md) · [Ngày 15 →](day-15.md)
