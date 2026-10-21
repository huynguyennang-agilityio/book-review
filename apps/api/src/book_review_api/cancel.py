"""Cờ huỷ theo `thread_id` (ngày 15).

Huỷ khi graph đang chạy không ghi được vào state (checkpoint đang do run đó nắm), nên endpoint
huỷ đặt cờ ở Redis. Graph kiểm cờ trước mỗi node, `ArqJobRunner` kiểm cờ khi chờ job của worker
và huỷ job đang chạy. Cờ hết hạn sau một ngày.
"""

import logging
from typing import Protocol

from redis import Redis

log = logging.getLogger(__name__)

CANCEL_TTL_S = 24 * 3600


class CancelFlags(Protocol):
    def set(self, thread_id: str) -> None: ...

    def is_set(self, thread_id: str) -> bool: ...


def cancel_key(thread_id: str) -> str:
    return f"br:cancel:{thread_id}"


class RedisCancelFlags:
    def __init__(self, redis_url: str) -> None:
        self._redis: Redis = Redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)

    def set(self, thread_id: str) -> None:
        self._redis.set(cancel_key(thread_id), "1", ex=CANCEL_TTL_S)

    def is_set(self, thread_id: str) -> bool:
        try:
            return bool(self._redis.exists(cancel_key(thread_id)))
        except Exception:  # noqa: BLE001
            # Redis tạm mất thì graph vẫn chạy tiếp, không coi như đã huỷ.
            log.warning("không đọc được cờ huỷ", exc_info=True)
            return False
