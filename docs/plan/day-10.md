# Ngày 10: Storyboard có citations, dataset golden bản đầu

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Kịch bản được viết từ các đoạn truy xuất, mỗi cảnh dữ kiện có trích dẫn nguồn, và có 10 sách golden đầu tiên.

## Phụ thuộc / chuẩn bị

- Ngày 9

## Công việc

### Storyboard

- [ ] Schema Pydantic `Citation`, `Scene`, `Storyboard` (mục 10 plan).
- [ ] Node `storyboard`: sinh dàn ý, sinh query theo từng phần, retrieve, viết từng phần bằng structured output, gắn `citations`.
- [ ] Validator: cảnh `context`/`body` bắt buộc có citation, `quote` ≤ 200 ký tự và phải có trong chunk.
- [ ] Prompt trong `prompts/storyboard_v1.md`.

### Dataset golden

- [ ] `evals/golden/`: 10 sách (5 fiction, 5 non-fiction), mỗi sách có bộ nguồn cố định và vài dữ kiện "phải đúng".

## Đầu ra

- Node storyboard + test validator
- 10 sách golden

## Tiêu chí hoàn thành

- [ ] Storyboard của 3 sách mẫu có citation hợp lệ ở mọi cảnh dữ kiện

---

[← Ngày 9](day-09.md) · [Mục lục](README.md) · [Ngày 11 →](day-11.md)
