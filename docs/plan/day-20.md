# Ngày 20: Bộ nhớ dài hạn, version prompt, PII trong log

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Lần chạy sau tự áp dụng sở thích đã lưu, mỗi run ghi version prompt, không lộ PII trong log và trace.

## Phụ thuộc / chuẩn bị

- Ngày 19

## Công việc

### Memory

- [ ] `memory/store.py`: `PostgresStore`, namespace `("users", user_id, ...)`: sở thích, lịch sử sách, nhân vật đã duyệt, phản hồi ở checkpoint.
- [ ] Node `save_memory` cuối mỗi run. `get_user_preferences` đọc dữ liệu thật.
- [ ] API `GET /me/memory`, `DELETE /me/memory` và màn cài đặt trên web.

### Prompts

- [ ] Loader prompt theo version, ghi `prompt_version` vào metadata run LangSmith.

### PII

- [ ] Mask PII trong log và trước khi gửi trace lên LangSmith (hide inputs/outputs hoặc hàm mask).

## Đầu ra

- Màn cài đặt bộ nhớ
- Test mask PII

## Tiêu chí hoàn thành

- [ ] Lần chạy thứ 2 tự áp dụng sở thích đã lưu

## Ghi chú

- Nếu cần rút ngắn tiến độ, có thể bỏ phần memory ở bản đầu (plan mục 13).

---

[← Ngày 19](day-19.md) · [Mục lục](README.md) · [Ngày 21 →](day-21.md)
