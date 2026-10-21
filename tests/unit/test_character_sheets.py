"""Node character_sheets với provider ảnh giả lập."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from test_graph import config
from test_graph import run as run_graph

from book_review_api.config import Settings
from book_review_api.errors import ErrorCode
from book_review_api.graph.build import build_graph
from book_review_api.graph.nodes.characters import (
    base_seed,
    make_character_sheets_node,
    make_regen_characters_node,
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


# --- Ngày 17: duyệt nhân vật, tạo lại ---


def candidates_state(tmp_path: Path, n_chars: int = 2) -> dict[str, Any]:
    node = make_character_sheets_node(FakeImages(), cfg(tmp_path), approved_lookup=no_store)
    out = run(node, {"storyboard": storyboard(n_chars)})
    return {"storyboard": storyboard(n_chars), "character_candidates": out["character_candidates"]}


def test_regen_makes_new_images_with_note(tmp_path: Path) -> None:
    state = candidates_state(tmp_path)
    old = state["character_candidates"]["nhan-vat-0"]["images"]
    fake = FakeImages()
    node = make_regen_characters_node(fake, cfg(tmp_path))
    out = run(node, {**state, "character_regen": {"nhan-vat-0": "tóc ngắn hơn"}})
    new = out["character_candidates"]["nhan-vat-0"]
    assert set(out["character_candidates"]) == {"nhan-vat-0"}
    assert len(new["images"]) == 4 and new["round"] == 1 and not set(new["images"]) & set(old)
    assert len(fake.calls) == 4 and all("tóc ngắn hơn" in c["prompt"] for c in fake.calls)
    assert all("no text" in c["prompt"] for c in fake.calls)
    assert out["cost"]["usd"] == 4 * 0.03
    assert out["character_regen"] is None


def test_regen_respects_budget_and_round_limit(tmp_path: Path) -> None:
    state = candidates_state(tmp_path, 1)
    fake = FakeImages()
    node = make_regen_characters_node(fake, cfg(tmp_path))
    out = run(
        node,
        {**state, "character_regen": {"nhan-vat-0": ""}, "options": {"budget_usd": 0.05}},
    )
    assert out["status"] == "failed" and out["error_code"] == ErrorCode.BUDGET_EXCEEDED.value
    assert fake.calls == [] and out["character_candidates"] == {}

    state["character_candidates"]["nhan-vat-0"]["round"] = 3
    out = run(node, {**state, "character_regen": {"nhan-vat-0": ""}})
    assert fake.calls == [] and out["character_candidates"] == {}


@pytest.fixture(autouse=True)
def tmp_media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "book_review_api.graph.nodes.characters.get_settings", lambda: cfg(tmp_path)
    )


def test_select_characters_and_continue_to_scene_images(tmp_path: Path) -> None:
    store = InMemoryStore()
    graph = build_graph(InMemorySaver(), store=store)
    state = candidates_state(tmp_path)
    run_graph(graph, {"book": {"title": "Nhà giả kim", "series": "Bộ thử"}})
    graph.update_state(config(), state, as_node="review_script")
    run_graph(graph, Command(resume={"approved": True}))
    paused = graph.get_state(config())
    assert paused.next == ("review_characters",)
    payload = paused.interrupts[0].value
    assert payload["type"] == "review_characters"
    assert payload["characters"]["nhan-vat-0"]["regen_left"] == 3

    visited = run_graph(graph, Command(resume={"selections": {"nhan-vat-0": 2, "nhan-vat-1": 0}}))
    assert "scene_images" in visited
    values = graph.get_state(config()).values
    chosen = state["character_candidates"]["nhan-vat-0"]["images"][2]
    assert values["characters_approved"]["nhan-vat-0"]["sheet_path"] == chosen
    assert values["asset_refs"]["character:nhan-vat-0:approved"] == chosen
    saved = store.get(("characters", "bo-thu"), "nhan-vat-0")
    assert saved is not None and saved.value["sheet_path"] == chosen


def test_missing_selection_fails_validation(tmp_path: Path) -> None:
    graph = build_graph(InMemorySaver())
    run_graph(graph, {"book": {"title": "Nhà giả kim"}})
    graph.update_state(config(), candidates_state(tmp_path), as_node="review_script")
    run_graph(graph, Command(resume={"approved": True}))
    visited = run_graph(graph, Command(resume={"selections": {"nhan-vat-0": 1}}))
    assert "scene_images" not in visited
    values = graph.get_state(config()).values
    assert values["status"] == "failed"
    assert values["error_code"] == ErrorCode.VALIDATION_ERROR.value


def test_regenerate_loops_back_to_review(tmp_path: Path) -> None:
    graph = build_graph(InMemorySaver(), image_provider=FakeImages())
    state = candidates_state(tmp_path)
    run_graph(graph, {"book": {"title": "Nhà giả kim"}})
    graph.update_state(config(), state, as_node="review_script")
    run_graph(graph, Command(resume={"approved": True}))
    visited = run_graph(
        graph,
        Command(resume={"selections": {"nhan-vat-1": 3}, "regenerate": {"nhan-vat-0": "đội mũ"}}),
    )
    assert "regen_characters" in visited and "scene_images" not in visited
    paused = graph.get_state(config())
    assert paused.next == ("review_characters",)
    payload = paused.interrupts[0].value
    assert payload["characters"]["nhan-vat-0"]["round"] == 1
    assert payload["characters"]["nhan-vat-0"]["regen_left"] == 2
    assert payload["picks"] == {"nhan-vat-1": 3}
    assert paused.values["cost"]["usd"] == pytest.approx(4 * 0.03)
    visited = run_graph(graph, Command(resume={"selections": {"nhan-vat-0": 0, "nhan-vat-1": 3}}))
    assert "scene_images" in visited
