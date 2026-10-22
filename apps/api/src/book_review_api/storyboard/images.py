"""Kế hoạch ảnh cảnh (ngày 18): mỗi cảnh cần mấy ảnh và prompt của từng ảnh.

`image_plan` thuần tuý theo storyboard nên `tts_align` (đặt `image_count` cho timeline) và
`scene_images` cùng tính ra một kết quả. Ảnh cảnh nào đã có `scene.images` thì giữ nguyên số đó.
"""

import logging
import math
import time
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from book_review_api.config import Settings
from book_review_api.providers.structured import StructuredOutputError, Usage, call_structured
from book_review_api.storyboard.schema import Scene, SceneType, Storyboard

log = logging.getLogger(__name__)

# Mỗi ảnh dùng cho 1-2 shot (video 3 phút chỉ có ~40 shot nên 2-3 shot/ảnh không đủ 25 ảnh).
# Tốc độ đọc tiếng Việt ước lượng (ký tự/giây) và độ dài shot trung bình, để đoán số shot.
CHARS_PER_S = 14.0
SHOT_TARGET_S = 4.5
SHOTS_PER_IMAGE = 1.5

SCENE_TYPE_HINT: dict[SceneType, str] = {
    "character": "a character portrait in a meaningful moment",
    "landscape": "a wide establishing landscape of the story world",
    "metaphor": "a symbolic, metaphorical still life that expresses the idea",
    "action": "a dynamic action moment",
    "title": "a clean, elegant symbolic composition suited to a title card",
}


class ImagePrompt(BaseModel):
    prompt_en: str
    # Cảnh ẩn dụ không có người, dùng khi prompt chính bị bộ lọc chặn.
    metaphor_en: str
    characters: list[str] = Field(default_factory=list)


ImagePrompts = dict[int, list[ImagePrompt]]
PromptWriter = Callable[[Storyboard, dict[int, int]], ImagePrompts]


def _estimated_shots(scene: Scene) -> int:
    return max(1, round(len(scene.narration_vi) / CHARS_PER_S / SHOT_TARGET_S))


def image_plan(storyboard: Storyboard, settings: Settings) -> dict[int, int]:
    """`{scene_id: số ảnh}`: mỗi ảnh dùng cho khoảng 2 shot, tổng nằm trong
    [`scene_images_min`, `scene_images_max`] nếu kịch bản đủ dài."""
    shots = {s.id: _estimated_shots(s) for s in storyboard.scenes}
    plan = {
        s.id: len(s.images) or math.ceil(shots[s.id] / SHOTS_PER_IMAGE) for s in storyboard.scenes
    }
    fixed = {s.id for s in storyboard.scenes if s.images}
    while sum(plan.values()) > settings.scene_images_max:
        cand = [i for i in plan if plan[i] > 1 and i not in fixed]
        if not cand:
            break
        plan[max(cand, key=lambda i: plan[i])] -= 1
    while sum(plan.values()) < settings.scene_images_min:
        cand = [i for i in plan if plan[i] < shots[i] and i not in fixed]
        if not cand:
            break
        plan[max(cand, key=lambda i: shots[i] - plan[i])] += 1
    return plan


def default_prompts(storyboard: Storyboard, plan: dict[int, int]) -> ImagePrompts:
    """Prompt tối thiểu khi không có model viết prompt: theo kiểu cảnh, tâm trạng, nhân vật."""
    people = storyboard.characters
    out: ImagePrompts = {}
    for scene in storyboard.scenes:
        items: list[ImagePrompt] = []
        for k in range(plan[scene.id]):
            who = (
                [people[(scene.id + k) % len(people)]]
                if people and scene.scene_type in ("character", "action")
                else []
            )
            base = f"{SCENE_TYPE_HINT[scene.scene_type]}, {scene.mood} mood"
            prompt = (
                f"{who[0].description_en.rstrip('.')}, {base}, composition {k + 1}"
                if who
                else f"{base}, composition {k + 1}"
            )
            metaphor = (
                f"a symbolic still life with no people, {scene.mood} mood, composition {k + 1}"
            )
            items.append(
                ImagePrompt(
                    prompt_en=prompt, metaphor_en=metaphor, characters=[w.name for w in who]
                )
            )
        out[scene.id] = items
    return out


class _ImageDraft(BaseModel):
    prompt_en: str = Field(description="Prompt tạo ảnh bằng tiếng Anh, 1-2 câu, tả cụ thể")
    metaphor_en: str = Field(
        description="Prompt thay thế: cảnh ẩn dụ/vật thể, KHÔNG có người, cùng ý nghĩa"
    )
    characters: list[str] = Field(
        default_factory=list, description="Tên nhân vật xuất hiện (tối đa 2, đúng như danh sách)"
    )


class _SceneDraft(BaseModel):
    scene_id: int
    images: list[_ImageDraft]


class _PromptSheet(BaseModel):
    scenes: list[_SceneDraft]


SYSTEM = (
    "Bạn viết prompt tạo ảnh dọc 9:16 cho video review sách. Với mỗi cảnh, viết đúng số prompt "
    "được yêu cầu, mỗi prompt một bố cục khác nhau (toàn cảnh, trung cảnh, cận cảnh) nhưng cùng "
    "ý của lời đọc. Prompt bằng tiếng Anh, không chứa chữ hay lời thoại để vẽ lên ảnh, không "
    "nhắc tên riêng của người thật, không bạo lực hay nội dung nhạy cảm. Chỉ cảnh có nhân vật "
    "trong danh sách mới điền `characters` (tối đa 2). Không tiết lộ kết truyện nếu lời đọc "
    "không nói tới. `metaphor_en` là cảnh thay thế an toàn không có người."
)


def make_prompt_writer(
    model: BaseChatModel,
    sleep: Callable[[float], None] = time.sleep,
) -> PromptWriter:
    """Một lần gọi model cho cả storyboard; lỗi hoặc thiếu cảnh thì dùng `default_prompts`."""

    def write(storyboard: Storyboard, plan: dict[int, int]) -> ImagePrompts:
        fallback = default_prompts(storyboard, plan)
        people = "\n".join(f"- {c.name}: {c.description_en}" for c in storyboard.characters)
        scenes = "\n".join(
            f"[cảnh {s.id}] loại={s.scene_type}, tâm trạng={s.mood}, số ảnh={plan[s.id]}\n"
            f"{s.narration_vi}"
            for s in storyboard.scenes
        )
        human = (
            f"Sách: {storyboard.book.title}\nPhong cách chung: {storyboard.style_prompt_en}\n"
            f"Nhân vật:\n{people or '(không có)'}\n\nCác cảnh:\n{scenes}"
        )
        try:
            sheet = call_structured(
                model, _PromptSheet, [SystemMessage(SYSTEM), HumanMessage(human)], Usage(), sleep
            )
        except (StructuredOutputError, Exception):  # noqa: BLE001
            log.warning(
                "không viết được prompt ảnh bằng model, dùng prompt mặc định", exc_info=True
            )
            return fallback
        known = {c.name for c in storyboard.characters}
        out: ImagePrompts = {}
        by_id = {d.scene_id: d.images for d in sheet.scenes}
        for sid, n in plan.items():
            drafts = by_id.get(sid, [])
            items = [
                ImagePrompt(
                    prompt_en=d.prompt_en.strip(),
                    metaphor_en=d.metaphor_en.strip() or fallback[sid][0].metaphor_en,
                    characters=[c for c in d.characters if c in known],
                )
                for d in drafts[:n]
                if d.prompt_en.strip()
            ]
            # Thiếu so với kế hoạch thì bù bằng prompt mặc định để số ảnh luôn khớp `image_count`.
            out[sid] = items + fallback[sid][len(items) :]
        return out

    return write
