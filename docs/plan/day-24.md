# Ngày 24: CI/CD (2/2): staging, smoke test, production, README

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Merge vào main tự deploy staging, production tạo được video thật.

## Phụ thuộc / chuẩn bị

- Ngày 23

## Công việc

### Deploy (`deploy.yml`)

- [ ] Merge main: build image, deploy API + worker (VPS hoặc Fly.io/Railway), web lên Vercel.
- [ ] Smoke test: 1 video ngắn với provider giả lập.
- [ ] Tag release: deploy production.

### Tài liệu

- [ ] README: kiến trúc, cách chạy local, biến môi trường, quy trình release.

## Đầu ra

- Staging và production chạy được
- README hoàn chỉnh

## Tiêu chí hoàn thành

- [ ] Merge vào main tự deploy staging
- [ ] Production tạo được video thật

## Ghi chú

- Kết thúc Giai đoạn 1. Đối chiếu Definition of Done (plan mục 16) trước khi sang giai đoạn đăng thử.

---

[← Ngày 23](day-23.md) · [Mục lục](README.md) · [Ngày 25 →](day-25.md)
