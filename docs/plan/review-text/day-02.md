# Ngày 2: Khung backend cho nguồn `user_review`

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Graph nhận đầu vào 3 ô, kiểm tra hợp lệ và bỏ qua research. Chưa sinh kịch bản.

## Phụ thuộc / chuẩn bị

- Ngày 4 (precheck, graph khung), ngày 5 (`normalize_text`, `mask_pii`)

## Công việc

- [x] **State**: `RunOptions.source: Literal["book", "user_review"]` (mặc định `"book"`); `BookReviewState.user_review: {hook?, main, comment?}`.
- [x] **Precheck** khi `source = user_review`:
  - Làm sạch bằng `normalize_text`.
  - Ý chính ≥ 100 từ; tổng thời lượng đọc ≤ 5 phút.
  - Hook > 20 từ thì ghi cảnh báo, không chặn.
  - Che PII bằng `mask_pii`.
  - Kiểm từ khoá tiên hiệp/kiếm hiệp trên tên sách **và** nội dung.
- [x] **Ghi chú khi làm**: code nằm ở `graph/nodes/review_text.py` (`clean_user_review`, `precheck_review`, node `ingest_review`). Mỗi ô giới hạn 20.000 ký tự trước khi làm sạch. Thời lượng đọc tính bằng `storyboard/duration.py` của ngày 1. `ingest_review` đi thẳng tới `estimate_cost`.
- [x] **Graph**: cạnh có điều kiện sau `precheck`: `book` → `research_agent`, `user_review` → `ingest_review` (hôm nay là stub, Ngày 3 làm thật).
- [x] **Mã lỗi**: `REVIEW_TOO_SHORT`, `REVIEW_TOO_LONG` kèm câu tiếng Việt trong `errors.py` và `ERROR_TEXT` của web.
- [x] **DB**: migration `0006_project_source.sql`, cột `projects.source text not null default 'book'`; `ProjectCreate` nhận `source`.
- [x] **Test**: tab cũ không đổi (research runner vẫn được gọi); tab mới không gọi research và `identify_confirm`; bài quá ngắn, quá dài, có từ "tu tiên" bị từ chối đúng mã; số điện thoại bị che; RLS không mở đọc chéo.

## Tiêu chí hoàn thành

- [x] Tab mới đi `precheck → ingest_review` không gọi research
- [x] Toàn bộ test tab cũ xanh

---

[← Ngày 1](day-01.md) · [Mục lục](README.md) · [Ngày 3 →](day-03.md)
