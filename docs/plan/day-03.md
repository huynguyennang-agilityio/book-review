# Ngày 3: Khung monorepo, FastAPI, Auth

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Dựng khung repo dùng lâu dài (uv workspace cho Python, pnpm cho web), FastAPI có xác thực JWT Supabase và bảng mã lỗi ổn định.

## Phụ thuộc / chuẩn bị

- Kết quả spike ngày 2 (version đã pin)
- Project Supabase (hoặc Supabase local qua CLI)

## Công việc

### Monorepo

- [ ] Hoàn thiện `pyproject.toml` gốc (uv workspace: `apps/api`, `apps/worker`), `pnpm-workspace.yaml` (`apps/web`).
- [ ] Cấu hình `ruff`, `mypy`, `pytest` ở gốc. Thêm `pre-commit` nếu muốn.
- [ ] Scaffold `apps/web` bằng `create-next-app` (TypeScript, App Router), thêm CopilotKit.

### API

- [ ] `apps/api`: `main.py` (app, `/health`), `config.py` (pydantic-settings, đọc `.env`).
- [ ] `auth.py`: verify JWT Supabase (JWKS hoặc secret), dependency `current_user` trả `user_id`.
- [ ] `errors.py`: enum mã lỗi (`BOOK_NOT_FOUND`, `GENRE_EXCLUDED`, `BUDGET_EXCEEDED`, `PROVIDER_UNAVAILABLE`, `LOW_FAITHFULNESS`, `RENDER_FAILED`, `CANCELLED`, ...), exception handler trả `{code, message_vi, retryable}`.

### Test

- [ ] Unit test: token hợp lệ, token hết hạn, thiếu token, mã lỗi trả đúng format.

## Đầu ra

- Repo chạy được `uv sync`, `uv run pytest`, `pnpm install`
- `/health` và một endpoint `/me` có auth

## Tiêu chí hoàn thành

- [ ] Gọi `/me` không có token trả 401 theo format mã lỗi
- [ ] Lint và test xanh ở local

## Ghi chú

- Không dùng service key của Supabase cho dữ liệu người dùng.

---

[← Ngày 2](day-02.md) · [Mục lục](README.md) · [Ngày 4 →](day-04.md)
