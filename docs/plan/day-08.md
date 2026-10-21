# Ngày 8: Research agent: tools

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Viết đủ 7 tool của research agent, mỗi tool có lỗi dạng cấu trúc và test riêng.

## Phụ thuộc / chuẩn bị

- Ngày 7

## Công việc

### Tools (`agents/tools.py`)

- [x] `web_search(query)`: Gemini có Google Search grounding, interface tách riêng để đổi sang Tavily.
- [x] `fetch_page(url)`: tải trang, trích nội dung bằng trafilatura.
- [x] `ingest_source(url, text)`: gọi pipeline ingestion ngày 5–6.
- [x] `search_knowledge(query)`: gọi retrieval ngày 7.
- [x] `lookup_book_identity(title, author?)`: trả tác giả, năm, tên gốc, danh sách sách trùng tên.
- [x] `check_genre(genre)`: trả cờ bị loại trừ.
- [x] `get_user_preferences()`: đọc Store (tạm trả mặc định nếu chưa có dữ liệu).

### Chuẩn hóa

- [x] Mọi tool trả `{error_code, message}` khi lỗi, không ném exception ra agent.
- [x] Đẩy event tiến độ (nguồn mới, nguồn đã đọc) để UI hiển thị sau này.

## Đầu ra

- `agents/tools.py` + unit test có mock provider

## Tiêu chí hoàn thành

- [x] Mỗi tool có test cho cả nhánh thành công và lỗi

---

[← Ngày 7](day-07.md) · [Mục lục](README.md) · [Ngày 9 →](day-09.md)
