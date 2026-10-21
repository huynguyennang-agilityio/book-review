"""Tiến độ job: worker ghi vào Redis, API đọc để hiển thị."""

from typing import Any

PROGRESS_TTL_S = 3600


def progress_key(job_id: str) -> str:
    return f"br:progress:{job_id}"


async def report_progress(ctx: dict[str, Any], done: int, total: int, note: str = "") -> None:
    """Ghi `done/total` cho job đang chạy. Bỏ qua khi chạy ngoài arq (không có redis)."""
    redis = ctx.get("redis")
    job_id = ctx.get("job_id")
    if redis is None or job_id is None:
        return
    key = progress_key(job_id)
    await redis.hset(key, mapping={"done": done, "total": total, "note": note})
    await redis.expire(key, PROGRESS_TTL_S)
