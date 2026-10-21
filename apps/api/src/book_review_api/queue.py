"""Đẩy job sang worker arq và chờ kết quả. Graph chỉ phụ thuộc `JobRunner` nên test thay được."""

import asyncio
from collections.abc import Awaitable
from typing import Any, Protocol, cast

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from langgraph.config import get_config

from book_review_api.cancel import CancelFlags
from book_review_api.graph.nodes.common import Cancelled


class JobFailed(Exception):
    """Job của worker lỗi hoặc quá hạn."""


class JobRunner(Protocol):
    def run(self, function: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ArqJobRunner:
    def __init__(
        self,
        redis_url: str,
        timeout_s: float = 600.0,
        cancel_flags: CancelFlags | None = None,
    ) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._timeout_s = timeout_s
        self._cancel_flags = cancel_flags

    def run(self, function: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Node của graph là hàm đồng bộ chạy trong thread riêng, nên không có event loop sẵn.
        return asyncio.run(self._run(function, payload, self._thread_id()))

    @staticmethod
    def _thread_id() -> str | None:
        try:
            thread_id = get_config().get("configurable", {}).get("thread_id")
        except RuntimeError:  # chạy ngoài graph (script)
            return None
        return str(thread_id) if thread_id else None

    def _cancelled(self, thread_id: str | None) -> bool:
        return bool(self._cancel_flags and thread_id and self._cancel_flags.is_set(thread_id))

    async def _run(
        self, function: str, payload: dict[str, Any], thread_id: str | None = None
    ) -> dict[str, Any]:
        pool = await create_pool(self._settings)
        try:
            job = await pool.enqueue_job(function, payload)
            if job is None:
                raise JobFailed(f"không đẩy được job {function} (trùng job_id)")
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._timeout_s
            while True:
                try:
                    result = await job.result(timeout=1.0, poll_delay=0.5)
                    break
                except TimeoutError as exc:
                    if self._cancelled(thread_id):
                        # Worker dừng job đang chạy; chi phí đã tiêu vẫn nằm trong state.
                        await job.abort(timeout=1)
                        raise Cancelled from exc
                    if loop.time() >= deadline:
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
