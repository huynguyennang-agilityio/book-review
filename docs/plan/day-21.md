# Ngày 21: Tối ưu chất lượng (1/2): dataset golden 20 sách, chunking và retrieval

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Có đủ 20 sách golden và cải thiện chất lượng truy xuất.

## Phụ thuộc / chuẩn bị

- Ngày 11 (baseline)
- Ngày 20

## Công việc

### Dataset

- [ ] Bổ sung thêm 10 sách (gồm sách ít phổ biến) để đủ 10 fiction, 10 non-fiction.

### Tinh chỉnh

- [ ] Thử kích thước chunk, overlap, top-k, reranker. Đo context precision/recall.
- [ ] Đẩy kết quả lên LangSmith experiments để so sánh.

## Đầu ra

- 20 sách golden
- Bảng so sánh cấu hình retrieval trong `docs/evals/`

## Tiêu chí hoàn thành

- [ ] Chọn được cấu hình retrieval tốt nhất dựa trên số liệu

---

[← Ngày 20](day-20.md) · [Mục lục](README.md) · [Ngày 22 →](day-22.md)
