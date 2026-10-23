"""Kiểm tra hướng ảnh cảnh: Seedream đôi khi vẽ cả cảnh nằm ngang 90° trong khung dọc.

Ảnh gốc Fal trả về vẫn là 1088×1920 và không có thẻ xoay EXIF, nên không sửa được bằng cách xoay
hay cắt ảnh. Ảnh được thu nhỏ rồi hỏi Gemini; lỗi model thì trả `unsure` để không chặn video.
"""

import base64
import io
import logging
import time
from collections.abc import Callable
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from PIL import Image
from pydantic import BaseModel, Field

from book_review_api.providers.structured import Usage, call_structured

log = logging.getLogger(__name__)

Orientation = Literal["upright", "rotated", "unsure"]
OrientationCheck = Callable[[bytes], Orientation]

# Đủ để thấy bố cục, ít token.
CHECK_SIZE = (360, 640)

PROMPT = (
    "This picture is meant to be shown in a vertical phone video frame. Look at the whole "
    "scene: people standing, faces, the horizon, floors, walls, furniture. Is it drawn upright, "
    "or is the entire scene turned sideways by 90 degrees (people lying along the long edge, "
    "horizon running top to bottom, so you would have to tilt your head to view it)? A person "
    "lying in bed or a tilted camera angle inside an upright scene still counts as upright. "
    "Answer `rotated` only when the whole picture is sideways; answer `unsure` if you cannot "
    "tell."
)


class _Answer(BaseModel):
    orientation: Orientation = Field(description="upright, rotated hoặc unsure")


def _thumbnail(data: bytes) -> str:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail(CHECK_SIZE)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode()


def make_orientation_checker(
    model: BaseChatModel,
    usage: Usage | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> OrientationCheck:
    usage = usage or Usage()

    def check(data: bytes) -> Orientation:
        message = HumanMessage(
            content=[
                {"type": "text", "text": PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{_thumbnail(data)}"},
                },
            ]
        )
        try:
            return call_structured(model, _Answer, [message], usage, sleep).orientation
        except Exception:  # noqa: BLE001
            log.warning("không kiểm tra được hướng ảnh, coi như unsure", exc_info=True)
            return "unsure"

    return check
