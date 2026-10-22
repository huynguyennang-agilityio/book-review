# Docker images

Build từ gốc repo:

```bash
docker build -f infra/docker/api.Dockerfile -t book-review-api .
docker build -f infra/docker/worker.Dockerfile -t book-review-worker .
docker build -f infra/docker/web.Dockerfile -t book-review-web .
```

- `api`: FastAPI (cổng 8000), cần `DATABASE_URL`, `REDIS_URL`, `GOOGLE_API_KEY`...
- `worker`: arq + edge-tts + FFmpeg/libass + font Việt.
- `web`: Next.js (cổng 3000); `NEXT_PUBLIC_*` truyền bằng `--build-arg`.
