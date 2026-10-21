"""Đẩy job sang worker arq và chờ kết quả. Graph chỉ phụ thuộc `JobRunner` nên test thay được."""

import asyncio
from collections.abc import Awaitable
from typing import Any, Protocol, cast

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus


class JobFailed(Exception):
    """Job của worker lỗi hoặc quá hạn."""


class JobRunner(Protocol):
    def run(self, function: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ArqJobRunner:
    def __init__(self, redis_url: str, timeout_s: float = 600.0) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._timeout_s = timeout_s

    def run(self, function: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Node của graph là hàm đồng bộ chạy trong thread riêng, nên không có event loop sẵn.
        return asyncio.run(self._run(function, payload))

    async def _run(self, function: str, payload: dict[str, Any]) -> dict[str, Any]:
        pool = await create_pool(self._settings)
        try:
            job = await pool.enqueue_job(function, payload)
            if job is None:
                raise JobFailed(f"không đẩy được job {function} (trùng job_id)")
            try:
                result = await job.result(timeout=self._timeout_s, poll_delay=0.5)
            except TimeoutError as exc:
                await job.abort(timeout=1)
                raise JobFailed(f"job {function} quá {self._timeout_s:.0f}s") from exc
            except Exception as exc:
                raise JobFailed(f"job {function} lỗi: {exc}") from exc
            if not isinstance(result, dict):
                raise JobFailed(f"job {function} trả kết quả không hợp lệ")
            return result
        finally:
            await pool.aclose()


async def job_progress(redis_url: str, job_id: str) -> dict[str, str]:
    """Đọc tiến độ `{done, total, note}` mà worker ghi cho job; rỗng nếu chưa có."""
    pool = await create_pool(RedisSettings.from_dsn(redis_url))
    try:
        raw = await cast(Awaitable[dict[bytes, bytes]], pool.hgetall(f"br:progress:{job_id}"))
        return {k.decode(): v.decode() for k, v in raw.items()}
    finally:
        await pool.aclose()


__all__ = ["ArqJobRunner", "Job", "JobFailed", "JobRunner", "JobStatus", "job_progress"]
