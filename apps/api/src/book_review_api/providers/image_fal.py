"""Provider tạo ảnh qua Fal (ngày 16). Graph chỉ phụ thuộc `ImageProvider` nên test thay được.

Sheet nhân vật dùng Seedream v4 text-to-image (cùng họ với model chỉnh ảnh đã chọn ở ADR 0003).
Mỗi lần gọi báo `request_id` của Fal qua `on_submit` ngay khi gửi, để lưu vào `fal_job_ids`;
khi người dùng huỷ, request đang chạy được `cancel` bên Fal.
"""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import fal_client
import httpx
from pydantic import BaseModel

from book_review_api.graph.nodes.common import Cancelled

log = logging.getLogger(__name__)

SEEDREAM_T2I = "fal-ai/bytedance/seedream/v4/text-to-image"
# Chỉnh theo ảnh tham chiếu (ADR 0003): dùng cho ảnh cảnh có nhân vật đã duyệt (ngày 18).
SEEDREAM_EDIT = "fal-ai/bytedance/seedream/v4/edit"
POLL_S = 1.0


class ImageError(Exception):
    """Fal lỗi, quá hạn hoặc không trả ảnh (vd bộ lọc an toàn chặn)."""


class ImageAccountError(ImageError):
    """Tài khoản Fal hết tiền, bị khoá, sai key hoặc bị giới hạn (429). Thử prompt khác không
    giúp gì: node dừng hẳn để người dùng nạp tiền rồi chạy lại."""


# Mã HTTP của Fal nghĩa là lỗi tài khoản chứ không phải lỗi của ảnh.
ACCOUNT_STATUS = {401, 402, 403, 429}


def _wrap(exc: Exception, message: str) -> ImageError:
    if isinstance(exc, fal_client.FalClientHTTPError) and exc.status_code in ACCOUNT_STATUS:
        return ImageAccountError(f"tài khoản Fal bị từ chối ({exc.status_code}): {exc}")
    return ImageError(f"{message}: {exc}")


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
        reference_images: Sequence[bytes] = (),
    ) -> GeneratedImage: ...


class FalImageProvider:
    def __init__(
        self,
        api_key: str,
        endpoint: str = SEEDREAM_T2I,
        edit_endpoint: str = SEEDREAM_EDIT,
        concurrency: int = 4,
        timeout_s: float = 240.0,
    ) -> None:
        self._client = fal_client.SyncClient(key=api_key)
        self._endpoint = endpoint
        self._edit_endpoint = edit_endpoint
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
        reference_images: Sequence[bytes] = (),
    ) -> GeneratedImage:
        with self._sem:
            return self._generate(
                prompt, seed, width, height, on_submit, cancelled, reference_images
            )

    def _generate(
        self,
        prompt: str,
        seed: int,
        width: int,
        height: int,
        on_submit: Callable[[str], None] | None,
        cancelled: Callable[[], bool] | None,
        reference_images: Sequence[bytes] = (),
    ) -> GeneratedImage:
        endpoint = self._endpoint
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "seed": seed,
            "image_size": {"width": width, "height": height},
            "num_images": 1,
            "enable_safety_checker": True,
        }
        if reference_images:
            endpoint = self._edit_endpoint
            try:
                arguments["image_urls"] = [
                    self._client.upload(data, "image/jpeg") for data in reference_images
                ]
            except Exception as exc:  # noqa: BLE001
                raise _wrap(exc, "không tải được ảnh tham chiếu lên Fal") from exc
        try:
            handle = self._client.submit(endpoint, arguments=arguments)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, "không gửi được yêu cầu tới Fal") from exc
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
            raise _wrap(exc, "Fal lỗi") from exc
        images = result.get("images") or []
        if not images:
            raise ImageError("Fal không trả ảnh (có thể bị bộ lọc an toàn chặn)")
        try:
            resp = httpx.get(images[0]["url"], timeout=60.0, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageError(f"không tải được ảnh: {exc}") from exc
        return GeneratedImage(data=resp.content, seed=result.get("seed"), job_id=handle.request_id)
