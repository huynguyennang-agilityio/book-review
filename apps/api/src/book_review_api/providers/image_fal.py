"""Provider tạo ảnh qua Fal (ngày 16). Graph chỉ phụ thuộc `ImageProvider` nên test thay được.

Sheet nhân vật dùng Seedream v4 text-to-image (cùng họ với model chỉnh ảnh đã chọn ở ADR 0003).
Mỗi lần gọi báo `request_id` của Fal qua `on_submit` ngay khi gửi, để lưu vào `fal_job_ids`;
khi người dùng huỷ, request đang chạy được `cancel` bên Fal.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import fal_client
import httpx
from pydantic import BaseModel

from book_review_api.graph.nodes.common import Cancelled

log = logging.getLogger(__name__)

SEEDREAM_T2I = "fal-ai/bytedance/seedream/v4/text-to-image"
POLL_S = 1.0


class ImageError(Exception):
    """Fal lỗi, quá hạn hoặc không trả ảnh (vd bộ lọc an toàn chặn)."""


class GeneratedImage(BaseModel):
    data: bytes
    seed: int | None = None
    job_id: str = ""


class ImageProvider(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        seed: int,
        width: int,
        height: int,
        on_submit: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> GeneratedImage: ...


class FalImageProvider:
    def __init__(
        self,
        api_key: str,
        endpoint: str = SEEDREAM_T2I,
        concurrency: int = 4,
        timeout_s: float = 240.0,
    ) -> None:
        self._client = fal_client.SyncClient(key=api_key)
        self._endpoint = endpoint
        self._sem = threading.BoundedSemaphore(concurrency)
        self._timeout_s = timeout_s

    def generate(
        self,
        prompt: str,
        *,
        seed: int,
        width: int,
        height: int,
        on_submit: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> GeneratedImage:
        with self._sem:
            return self._generate(prompt, seed, width, height, on_submit, cancelled)

    def _generate(
        self,
        prompt: str,
        seed: int,
        width: int,
        height: int,
        on_submit: Callable[[str], None] | None,
        cancelled: Callable[[], bool] | None,
    ) -> GeneratedImage:
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "seed": seed,
            "image_size": {"width": width, "height": height},
            "num_images": 1,
            "enable_safety_checker": True,
        }
        try:
            handle = self._client.submit(self._endpoint, arguments=arguments)
        except Exception as exc:  # noqa: BLE001
            raise ImageError(f"không gửi được yêu cầu tới Fal: {exc}") from exc
        if on_submit:
            on_submit(handle.request_id)
        deadline = time.monotonic() + self._timeout_s
        try:
            while True:
                if cancelled and cancelled():
                    handle.cancel()
                    raise Cancelled
                if time.monotonic() >= deadline:
                    handle.cancel()
                    raise ImageError(f"Fal quá {self._timeout_s:.0f}s")
                if isinstance(handle.status(), fal_client.Completed):
                    break
                time.sleep(POLL_S)
            result = handle.get()
        except (Cancelled, ImageError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ImageError(f"Fal lỗi: {exc}") from exc
        images = result.get("images") or []
        if not images:
            raise ImageError("Fal không trả ảnh (có thể bị bộ lọc an toàn chặn)")
        try:
            resp = httpx.get(images[0]["url"], timeout=60.0, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageError(f"không tải được ảnh: {exc}") from exc
        return GeneratedImage(data=resp.content, seed=result.get("seed"), job_id=handle.request_id)
