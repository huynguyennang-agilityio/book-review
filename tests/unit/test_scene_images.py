"""Node scene_images (ngày 18) với provider ảnh giả lập."""

import io
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from book_review_api.config import Settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.scene_images import (
    compose_prompt,
    fit_9_16,
    make_scene_images_node,
)
from book_review_api.providers.image_fal import GeneratedImage, ImageError
from book_review_api.storyboard.images import default_prompts, image_plan
from book_review_api.storyboard.schema import Storyboard


def png(w: int, h: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (90, 120, 200)).save(out, format="PNG")
    return out.getvalue()


class FakeImages:
    def __init__(self, block: Callable[[str], bool] | None = None, fail_all: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.block = block
        self.fail_all = fail_all
        self._lock = threading.Lock()

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
        with self._lock:
            n = len(self.calls)
            self.calls.append(
                {"prompt": prompt, "seed": seed, "w": width, "h": height,
                 "refs": len(reference_images)}
            )  # fmt: skip
        if on_submit:
            on_submit(f"req-{n}")
        if self.fail_all or (self.block and self.block(prompt)):
            raise ImageError("safety")
        return GeneratedImage(data=png(width, height), seed=seed, job_id=f"req-{n}")


def storyboard(scenes: int = 6, long: bool = False) -> dict[str, Any]:
    text = "Một câu lời đọc khá dài để có nhiều shot trong cảnh. " * (6 if long else 1)
    return {
        "book": {"title": "Sách thử"},
        "book_category": "fiction",
        "spoiler_free": True,
        "hook_vi": "x",
        "style_prompt_en": "soft watercolor",
        "caption_vi": "x",
        "characters": [
            {"name": "An", "description_en": "a boy, brown hair"},
            {"name": "Bình", "description_en": "a girl, red coat"},
            {"name": "Chi", "description_en": "an old man"},
        ],
        "scenes": [
            {
                "id": i + 1,
                "section": "body",
                "narration_vi": text,
                "scene_type": "character" if i % 2 == 0 else "landscape",
                "mood": "warm",
            }
            for i in range(scenes)
        ],
    }


def cfg(tmp_path: Path, **kw: Any) -> Settings:
    return Settings(media_dir=str(tmp_path), fal_concurrency=2, **kw)


def approved(tmp_path: Path) -> dict[str, Any]:
    out = {}
    for name, slug in (("An", "an"), ("Bình", "binh"), ("Chi", "chi")):
        p = tmp_path / "characters" / f"{slug}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(png(64, 36))
        out[slug] = {"name": name, "sheet_path": p.relative_to(tmp_path).as_posix()}
    return out


def test_fit_9_16_crops_exactly() -> None:
    for size in [(1088, 1920), (1920, 1080), (800, 2000)]:
        img = Image.open(io.BytesIO(fit_9_16(png(*size), 720, 1280)))
        assert img.size == (720, 1280)


def test_generation_size_is_multiple_of_16_near_9_16(tmp_path: Path) -> None:
    c = cfg(tmp_path)
    assert c.scene_image_width % 16 == 0 and c.scene_image_height % 16 == 0
    assert abs(c.scene_image_width / c.scene_image_height - 9 / 16) < 0.01


def test_plan_is_within_25_35_for_long_script(tmp_path: Path) -> None:
    sb = Storyboard.model_validate(storyboard(scenes=12, long=True))
    plan = image_plan(sb, cfg(tmp_path))
    assert 25 <= sum(plan.values()) <= 35
    assert all(n >= 1 for n in plan.values())


def test_plan_keeps_existing_images() -> None:
    raw = storyboard(2)
    raw["scenes"][0]["images"] = [{"prompt_en": "a"}, {"prompt_en": "b"}]
    plan = image_plan(Storyboard.model_validate(raw), Settings())
    assert plan[1] == 2


def test_generates_all_images_cropped_with_refs_for_max_two_characters(tmp_path: Path) -> None:
    provider = FakeImages()
    c = cfg(tmp_path)
    sb = Storyboard.model_validate(storyboard(4, long=True))
    plan = image_plan(sb, c)
    prompts = default_prompts(sb, plan)
    prompts[1][0].characters = ["An", "Bình", "Chi"]  # 3 người: chỉ giữ 2
    out = make_scene_images_node(provider, c, prompt_writer=lambda s, p: prompts)(
        {"storyboard": storyboard(4, long=True), "characters_approved": approved(tmp_path)}
    )
    assert "status" not in out
    refs = out["asset_refs"]
    assert len(refs) == sum(plan.values())
    first = Image.open(tmp_path / refs["image:1:0"])
    assert first.size == (720, 1280)
    assert max(call["refs"] for call in provider.calls) == 2
    assert all(call["w"] == c.scene_image_width for call in provider.calls)
    assert out["cost"]["images"] == float(len(provider.calls))
    scene_images = out["storyboard"]["scenes"][0]["images"]
    assert len(scene_images) == plan[1] and scene_images[0]["path"] == refs["image:1:0"]


def test_rerun_uses_cache_and_costs_nothing(tmp_path: Path) -> None:
    provider = FakeImages()
    node = make_scene_images_node(provider, cfg(tmp_path))
    state: Any = {"storyboard": storyboard(3), "characters_approved": approved(tmp_path)}
    first = node(state)
    calls = len(provider.calls)
    second = node(state)
    assert len(provider.calls) == calls
    assert second["cost"]["usd"] == 0.0
    assert second["asset_refs"] == first["asset_refs"]


def test_blocked_prompt_falls_back_to_metaphor(tmp_path: Path) -> None:
    provider = FakeImages(block=lambda p: "symbolic still life" not in p)
    node = make_scene_images_node(provider, cfg(tmp_path))
    out = node({"storyboard": storyboard(2)})
    assert "status" not in out
    assert any("symbolic still life" in c["prompt"] and c["refs"] == 0 for c in provider.calls)
    # Chạy lại: ảnh ẩn dụ đã có nên không gọi Fal nữa, kể cả prompt chính từng bị chặn.
    n = len(provider.calls)
    node({"storyboard": storyboard(2)})
    assert len(provider.calls) == n


def test_borrows_nearest_image_when_both_attempts_fail(tmp_path: Path) -> None:
    provider = FakeImages(block=lambda p: "composition 1" in p and "Vertical" in p)
    sbd = storyboard(3, long=True)
    out = make_scene_images_node(provider, cfg(tmp_path))({"storyboard": sbd})
    assert "status" not in out
    assert all(tmp_path.joinpath(p).exists() for p in out["asset_refs"].values())


def test_all_fail_reports_provider_unavailable(tmp_path: Path) -> None:
    out = make_scene_images_node(FakeImages(fail_all=True), cfg(tmp_path))(
        {"storyboard": storyboard(2)}
    )
    assert out["status"] == "failed"
    assert out["error_code"] == ErrorCode.PROVIDER_UNAVAILABLE.value


def test_stops_when_budget_exceeded(tmp_path: Path) -> None:
    provider = FakeImages()
    out = make_scene_images_node(provider, cfg(tmp_path))(
        {"storyboard": storyboard(4), "options": {"budget_usd": 0.06}, "cost": {"usd": 0.0}}
    )
    assert out["error_code"] == ErrorCode.BUDGET_EXCEEDED.value
    assert len(provider.calls) == 2


def test_missing_storyboard_fails(tmp_path: Path) -> None:
    out = make_scene_images_node(FakeImages(), cfg(tmp_path))({})
    assert out["error_code"] == ErrorCode.INTERNAL_ERROR.value


def test_compose_prompt_names_reference_images() -> None:
    p = compose_prompt("watercolor.", "a boy walks", ["An", "Bình"])
    assert "image 1 is An" in p and "image 2 is Bình" in p
    assert p.endswith("no logo.") and "watercolor. Vertical" in p
    assert "Reference" not in compose_prompt("s", "x", [])
