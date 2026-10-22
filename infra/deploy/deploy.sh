#!/usr/bin/env bash
# Chạy trên VPS: kéo image mới, migrate DB, khởi động lại. Dùng: REGISTRY=ghcr.io/o/r IMAGE_TAG=sha-abc ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
export IMAGE_TAG="${IMAGE_TAG:?thiếu IMAGE_TAG}"
export REGISTRY="${REGISTRY:?thiếu REGISTRY}"
touch .env
grep -vE '^(IMAGE_TAG|REGISTRY)=' .env > .env.new || true
printf 'IMAGE_TAG=%s\nREGISTRY=%s\n' "$IMAGE_TAG" "$REGISTRY" >> .env.new
mv .env.new .env
docker compose pull
docker compose run --rm api uv run --no-sync python -m book_review_api.migrate
docker compose up -d --remove-orphans
for _ in $(seq 1 30); do
  curl -fsS http://localhost:8000/health >/dev/null && { echo "API sẵn sàng"; exit 0; }
  sleep 2
done
echo "API không lên" >&2; docker compose logs --tail 50 api >&2; exit 1
