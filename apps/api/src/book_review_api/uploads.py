"""Kiểm tra và lưu ảnh người dùng tải lên (chế độ chọn ảnh manual).

Ảnh được chuẩn hoá thành JPEG không EXIF, đặt tên theo hash nội dung nên tải lại cùng ảnh không
tốn thêm chỗ. Ảnh nhỏ hơn 720x1280 hoặc lệch tỉ lệ 9:16 vẫn nhận kèm cảnh báo; bước dựng sẽ crop
giữa."""

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError

from book_review_api.errors import AppError, ErrorCode

MAX_BYTES = 10 * 1024 * 1024
MAX_PER_PROJECT = 60
TARGET_W, TARGET_H = 720, 1280
ASPECT_TOLERANCE = 0.02
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
JPEG_QUALITY = 92

# Tên file do chính API tạo ra: <sha256 rút gọn>.jpg
UPLOAD_NAME = re.compile(r"[0-9a-f]{32}\.jpg")


@dataclass(frozen=True)
class ImageWarning:
    code: str
    message_vi: str


@dataclass(frozen=True)
class Processed:
    data: bytes
    name: str
    width: int
    height: int
    warnings: list[ImageWarning]


def upload_dir(media_dir: str, project_id: UUID) -> Path:
    return Path(media_dir).resolve() / "uploads" / str(project_id)


def upload_rel_path(project_id: UUID, name: str) -> str:
    return f"uploads/{project_id}/{name}"


def is_upload_path(project_id: UUID, path: str) -> bool:
    """`path` đúng dạng `uploads/<project_id>/<hash>.jpg` của chính project này."""
    parts = path.split("/")
    return (
        len(parts) == 3
        and parts[0] == "uploads"
        and parts[1] == str(project_id)
        and UPLOAD_NAME.fullmatch(parts[2]) is not None
    )


def process_image(raw: bytes) -> Processed:
    if len(raw) > MAX_BYTES:
        raise AppError(ErrorCode.IMAGE_TOO_LARGE)
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
    except UnidentifiedImageError:
        raise AppError(ErrorCode.UNSUPPORTED_IMAGE) from None
    except (OSError, Image.DecompressionBombError):
        raise AppError(ErrorCode.INVALID_IMAGE) from None
    if fmt not in ALLOWED_FORMATS:
        raise AppError(ErrorCode.UNSUPPORTED_IMAGE)
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()  # giải mã hết để bắt file cắt cụt/hỏng
            upright = ImageOps.exif_transpose(img)  # xoay theo EXIF trước khi bỏ EXIF
            if upright.mode in ("RGBA", "LA", "P"):
                rgba = upright.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = upright.convert("RGB")
            width, height = rgb.size
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=JPEG_QUALITY)  # không truyền exif: bị bỏ
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise AppError(ErrorCode.INVALID_IMAGE) from None
    data = out.getvalue()
    warnings: list[ImageWarning] = []
    if width < TARGET_W or height < TARGET_H:
        warnings.append(
            ImageWarning(
                "LOW_RESOLUTION",
                f"Ảnh {width}×{height} nhỏ hơn {TARGET_W}×{TARGET_H}, video có thể bị mờ.",
            )
        )
    if abs(width / height - TARGET_W / TARGET_H) > ASPECT_TOLERANCE * (TARGET_W / TARGET_H):
        warnings.append(ImageWarning("ASPECT_MISMATCH", "Ảnh lệch tỉ lệ 9:16, phần rìa sẽ bị cắt."))
    name = hashlib.sha256(data).hexdigest()[:32] + ".jpg"
    return Processed(data, name, width, height, warnings)
