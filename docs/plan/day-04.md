# Ngày 4: Migrations, RLS, graph khung, precheck

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Có schema DB với RLS và test cô lập dữ liệu, cùng graph `book_review` khung chạy và resume được với node `precheck` thật.

## Phụ thuộc / chuẩn bị

- Ngày 3

## Công việc

### DB

- [ ] `db/migrations/`: bảng `projects`, `assets`, `documents`, `chunks` (riêng tư), cột `user_id`.
- [ ] Bật RLS mọi bảng ứng dụng, policy `user_id = auth.uid()`.
- [ ] Backend truy vấn bằng JWT của người dùng (set role/claims theo request).

### Test RLS

- [ ] Test tích hợp với Postgres trong container: user A tạo project, user B không đọc, sửa, xóa được.

### Graph

- [ ] `graph/state.py`: `BookReviewState` (book, research, storyboard, timeline, asset_refs, fal_job_ids, cost, eval_scores, status, cancel_requested).
- [ ] `graph/build.py`: `StateGraph` với đủ tên node của mục 2.1, node chưa làm thì là stub. Gắn `PostgresSaver` và `PostgresStore`.
- [ ] Node `precheck`: blacklist thể loại tiên hiệp, kiếm hiệp, huyền huyễn tu tiên, võ hiệp theo từ khóa tên sách, không gọi API.
- [ ] Helper `check_cancel(state)` gọi đầu mỗi node.

### API

- [ ] `POST /projects` tạo project + `thread_id`, `GET /projects/{id}`.

## Đầu ra

- Migration chạy được từ DB trống
- Test RLS và test graph resume

## Tiêu chí hoàn thành

- [ ] User A không đọc được dữ liệu của user B (có test tự động)
- [ ] Graph khung chạy, dừng giữa chừng, resume được

## Ghi chú

- Ghi rõ cách chạy migration trong README.

---

[← Ngày 3](day-03.md) · [Mục lục](README.md) · [Ngày 5 →](day-05.md)
