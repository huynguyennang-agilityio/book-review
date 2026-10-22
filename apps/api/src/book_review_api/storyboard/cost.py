"""Ước tính chi phí media theo storyboard, hiện ở checkpoint duyệt kịch bản (mục 14 plan v5).

Chỉ là ước lượng trước khi chạy: số ảnh theo `image_plan` (25-35 ảnh/video);
TTS tính theo số ký tự lời đọc; I2V theo số clip định animate.
"""

from book_review_api.config import Settings, get_settings
from book_review_api.storyboard.images import image_plan
from book_review_api.storyboard.schema import Storyboard


def estimate_media_cost(
    storyboard: Storyboard, settings: Settings | None = None
) -> dict[str, float]:
    s = settings or get_settings()
    scene_images = sum(image_plan(storyboard, s).values())
    character_images = len(storyboard.characters) * s.character_sheet_images
    images = scene_images + character_images
    tts_chars = sum(len(sc.narration_vi) for sc in storyboard.scenes)
    clips = min(s.i2v_clips, len(storyboard.scenes))
    images_usd = images * s.price_image_usd
    tts_usd = tts_chars * s.price_tts_per_mchar / 1e6
    i2v_usd = clips * s.price_i2v_per_clip
    total = images_usd + tts_usd + i2v_usd
    return {
        "images": float(images),
        "character_images": float(character_images),
        "scene_images": float(scene_images),
        "images_usd": images_usd,
        "tts_chars": float(tts_chars),
        "tts_usd": tts_usd,
        "i2v_clips": float(clips),
        "i2v_usd": i2v_usd,
        "total_usd": total,
        # Chế độ manual không gọi Fal: tiền ảnh = 0, người dùng tự tải ảnh.
        "manual_total_usd": total - images_usd,
        "manual_saving_usd": images_usd,
    }
