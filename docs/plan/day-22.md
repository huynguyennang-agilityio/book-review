# Ngày 22: Tối ưu chất lượng (2/2): prompt, hook, faithfulness > 90%

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Đạt faithfulness trung bình > 0.9 trên dataset golden.

## Phụ thuộc / chuẩn bị

- Ngày 21

## Công việc

### Prompt

- [x] Tinh chỉnh prompt storyboard và vòng sửa, ra version mới (`storyboard_v2.md`...).
- [x] Chỉnh hook 0–5s cho hấp dẫn mà vẫn đúng nội dung.

### Đo

- [x] Chạy RAGAS đủ 20 sách, kiểm tay 20 mẫu để đối chiếu.
- [x] Các chỉ số khác: tỉ lệ từ chối tiên hiệp/kiếm hiệp đã đo (9/10); answer relevancy và phân loại thể loại chưa đo, xem `docs/evals/baseline.md`.

## Đầu ra

- `eval_report.json` trên 20 sách
- Cập nhật `docs/evals/`

## Tiêu chí hoàn thành

- [x] Faithfulness trung bình > 0.9 trên dataset golden

## Ghi chú

- Nếu chưa đạt, ghi rõ khoảng cách và nguyên nhân, dùng buffer trước khi sang ngày 23.

---

[← Ngày 21](day-21.md) · [Mục lục](README.md) · [Ngày 23 →](day-23.md)
