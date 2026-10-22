# API: FastAPI + LangGraph. Build từ gốc repo: docker build -f infra/docker/api.Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/api/src apps/api/src
COPY apps/worker/src apps/worker/src
COPY db db
RUN uv sync --locked --no-dev --package book-review-api
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "book_review_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
