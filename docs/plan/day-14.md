# Ngày 14: Frontend: đăng nhập, chat, tiến độ

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Người dùng đăng nhập trên web, nhập tên sách, xem agent research và tiến độ graph theo thời gian thực.

## Phụ thuộc / chuẩn bị

- Ngày 13
- Spike CopilotKit ngày 2

## Công việc

### Web

- [x] Đăng nhập Supabase Auth, gửi JWT tới API và endpoint AG-UI. (Đăng nhập thật với Supabase chưa thử; luồng chạy bằng JWT thử ký cho Postgres local.)
- [x] Màn chat: nhập tên sách và tùy chọn (độ dài, no_spoiler, giọng, ngân sách).
- [x] Hiển thị danh sách nguồn hiện dần, nguồn đã đọc, nguồn dùng cho kịch bản.
- [x] Màn chọn đúng sách khi `identify_confirm` interrupt.
- [x] Thanh tiến độ theo node.

### API

- [x] Endpoint `/agent` kiểm tra JWT, stream event tiến độ, tool call, state, interrupt.

## Ghi chú

- Tuỳ chọn (độ dài, no_spoiler, giọng, ngân sách) đã lưu vào `state.options`; node sau đọc dần, ngày 14 chưa node nào dùng.
- Từ ngày 14 `/agent` chạy graph thật với research agent (cần `GOOGLE_API_KEY`); các node sau `identify_confirm` vẫn là node rỗng cho tới khi nối ở các ngày sau, nên run dừng ở `review_script`.
- Tiến độ vẽ từ event tuỳ biến `node` do graph phát, không dùng `STEP_*` của adapter vì lẫn tên bước nội bộ của research agent.
- Chạy thử qua dòng lệnh: `scripts/run_agent.py`.

## Đầu ra

- Luồng đăng nhập → nhập sách → xem research chạy được trên web

## Tiêu chí hoàn thành

- [x] Từ web khởi động được một project và thấy tiến độ thật

---

[← Ngày 13](day-13.md) · [Mục lục](README.md) · [Ngày 15 →](day-15.md)
