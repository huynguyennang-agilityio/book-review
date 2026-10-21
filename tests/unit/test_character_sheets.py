"""Node character_sheets với provider ảnh giả lập."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from book_review_api.config import Settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.characters import (
    base_seed,
    make_character_sheets_node,
    sheet_prompt,
    slugify,
)
from book_review_api.graph.state import BookReviewState
from book_review_api.providers.image_fal import GeneratedImage, ImageError
from book_review_api.storyboard.schema import Character


class FakeImages:
    def __init__(self, fail_first: bool = False, always_fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_first = fail_first
        self.always_fail = always_fail
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
    ) -> GeneratedImage:
        with self._lock:
            n = len(self.calls)
            self.calls.append({"prompt": prompt, "seed": seed, "w": width, "h": height})
        if on_submit:
            on_submit(f"req-{n}")
        if self.always_fail or (self.fail_first and n == 0):
            raise ImageError("safety")
        return GeneratedImage(data=b"jpg", seed=seed, job_id=f"req-{n}")


def storyboard(n_chars: int = 2) -> dict[str, Any]:
    return {
        "book": {"title": "Sách thử"},
        "book_category": "fiction",
        "spoiler_free": True,
        "hook_vi": "x",
        "style_prompt_en": "soft watercolor",
        "caption_vi": "x",
        "characters": [
            {"name": f"Nhân vật {i}", "description_en": f"a boy number {i}, brown hair"}
            for i in range(n_chars)
        ],
        "scenes": [
            {
                "id": 1,
                "section": "hook",
                "narration_vi": "a",
                "scene_type": "title",
                "mood": "warm",
            }
        ],
    }


def cfg(tmp_path: Path) -> Settings:
    return Settings(media_dir=str(tmp_path), character_sheet_images=4, fal_concurrency=2)


def run(node: Any, state: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = node(state)
    return result


def no_store(series: str | None, slug: str) -> None:
    return None


def test_four_candidates_per_character_with_fixed_seeds(tmp_path: Path) -> None:
    fake = FakeImages()
    node = make_character_sheets_node(fake, cfg(tmp_path), approved_lookup=no_store)
    out = run(node, {"storyboard": storyboard(2)})
    assert "status" not in out
    cands = out["character_candidates"]
    assert len(cands) == 2
    assert all(len(c["images"]) == 4 for c in cands.values())
    assert all((tmp_path / p).read_bytes() == b"jpg" for c in cands.values() for p in c["images"])
    assert out["cost"]["usd"] == 8 * 0.03
    assert len(out["fal_job_ids"]) == 8
    seeds = sorted(c["seed"] for c in fake.calls if "number 0" in c["prompt"])
    assert seeds == [base_seed("Nhân vật 0") + i for i in range(4)]
    assert all("no text" in c["prompt"] for c in fake.calls)


def test_rerun_reuses_files_and_costs_nothing(tmp_path: Path) -> None:
    node = make_character_sheets_node(FakeImages(), cfg(tmp_path), approved_lookup=no_store)
    run(node, {"storyboard": storyboard(1)})
    fake = FakeImages()
    node2 = make_character_sheets_node(fake, cfg(tmp_path), approved_lookup=no_store)
    out = run(node2, {"storyboard": storyboard(1)})
    assert fake.calls == []
    assert out["cost"]["usd"] == 0
    assert len(out["character_candidates"]["nhan-vat-0"]["images"]) == 4


def test_approved_character_of_series_is_reused(tmp_path: Path) -> None:
    fake = FakeImages()

    def lookup(series: str | None, slug: str) -> dict[str, Any] | None:
        assert series == "Dune"
        return {"sheet_path": "characters/old/a.jpg"} if slug == "nhan-vat-0" else None

    node = make_character_sheets_node(fake, cfg(tmp_path), approved_lookup=lookup)
    out = run(node, {"storyboard": storyboard(2), "book": {"title": "x", "series": "Dune"}})
    assert out["character_candidates"]["nhan-vat-0"]["reused"] is True
    assert out["asset_refs"]["character:nhan-vat-0:approved"] == "characters/old/a.jpg"
    assert len(fake.calls) == 4  # chỉ nhân vật chưa duyệt
    assert out["cost"]["usd"] == 4 * 0.03


def test_stops_when_budget_exceeded(tmp_path: Path) -> None:
    fake = FakeImages()
    node = make_character_sheets_node(fake, cfg(tmp_path), approved_lookup=no_store)
    state: BookReviewState = {
        "storyboard": storyboard(2),
        "options": {"budget_usd": 0.10},
        "cost": {"usd": 0.01},
    }
    out = run(node, dict(state))
    assert out["status"] == "failed"
    assert out["error_code"] == ErrorCode.BUDGET_EXCEEDED.value
    assert len(fake.calls) == 3  # (0,10 - 0,01) / 0,03 = 3 ảnh
    assert out["cost"]["usd"] == 3 * 0.03


def test_filtered_prompt_retries_with_neutral_description(tmp_path: Path) -> None:
    fake = FakeImages(fail_first=True)
    node = make_character_sheets_node(fake, cfg(tmp_path), approved_lookup=no_store)
    out = run(node, {"storyboard": storyboard(1)})
    assert "status" not in out
    assert any("friendly adult person" in c["prompt"] for c in fake.calls)
    assert len(out["character_candidates"]["nhan-vat-0"]["images"]) == 4


def test_provider_down_fails_with_code(tmp_path: Path) -> None:
    node = make_character_sheets_node(
        FakeImages(always_fail=True), cfg(tmp_path), approved_lookup=no_store
    )
    out = run(node, {"storyboard": storyboard(1)})
    assert out["error_code"] == ErrorCode.PROVIDER_UNAVAILABLE.value
    assert out["cost"]["usd"] == 0


def test_no_characters_is_a_noop(tmp_path: Path) -> None:
    fake = FakeImages()
    node = make_character_sheets_node(fake, cfg(tmp_path), approved_lookup=no_store)
    out = run(node, {"storyboard": storyboard(0)})
    assert out == {"character_candidates": {}} and fake.calls == []


def test_cancelled_state_skips_node(tmp_path: Path) -> None:
    fake = FakeImages()
    node = make_character_sheets_node(fake, cfg(tmp_path), approved_lookup=no_store)
    out = run(node, {"storyboard": storyboard(1), "cancel_requested": True})
    assert out["status"] == "cancelled" and fake.calls == []


def test_helpers() -> None:
    assert slugify("Nguyễn Văn Á") == "nguyen-van-a"
    assert slugify("???") == "nhan-vat"
    assert base_seed("a") == base_seed("a") != base_seed("b")
    p = sheet_prompt(Character(name="x", description_en="a girl."), "flat style.", 2)
    assert "a girl, " not in p and "no text" in p and "flat style." in p
