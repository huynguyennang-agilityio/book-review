# Ngày 23: CI/CD (1/2): GitHub Actions và Docker images

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Mỗi PR tự chạy lint, test và eval, có Docker image cho 3 app.

## Phụ thuộc / chuẩn bị

- Ngày 22

## Công việc

### CI (`.github/workflows/ci.yml`)

- [ ] Lint `ruff`, `mypy`, `eslint`. Unit test (timeline, phụ đề, RLS, mã lỗi).
- [ ] Integration test với Postgres + pgvector service container.

### Evals (`evals.yml`)

- [ ] Chạy khi PR đổi prompt, chunking, retrieval hoặc model: RAGAS trên 5 sách, chặn merge nếu < 0.9.

### Docker

- [ ] `infra/docker/api.Dockerfile`, `worker.Dockerfile` (FFmpeg + libass + font Việt), `web.Dockerfile`.

## Đầu ra

- 3 workflow chạy xanh trên một PR thử

## Tiêu chí hoàn thành

- [ ] PR thử chạy đủ lint, test, eval

## Ghi chú

- Secrets để trong GitHub Environments.

---

[← Ngày 22](day-22.md) · [Mục lục](README.md) · [Ngày 24 →](day-24.md)
