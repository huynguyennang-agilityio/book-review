# Worker render: arq + edge-tts + ffmpeg. Image đầy đủ cho api/web làm ở ngày 23.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker apps/worker
COPY apps/api/src apps/api/src
RUN uv sync --locked --no-dev --package book-review-worker
CMD ["uv", "run", "--no-sync", "arq", "book_review_worker.main.WorkerSettings"]
