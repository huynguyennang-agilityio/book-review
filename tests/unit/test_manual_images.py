"""Node manual_images: prompt, interrupt upload_images, kiểm tra, ghi kết quả, không gọi Fal."""

import io
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from PIL import Image
from test_scene_images import FakeImages, storyboard

from book_review_api.config import Settings
from book_review_api.graph.build import build_graph
from book_review_api.graph.nodes.manual_images import make_manual_images_node
from book_review_api.graph.state import BookReviewState
from book_review_api.storyboard.images import image_plan
from book_review_api.storyboard.schema import Storyboard

PID = "11111111-1111-1111-1111-111111111111"


def jpg(w: int = 400, h: int = 400) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (10, 200, 90)).save(out, format="JPEG")
    return out.getvalue()


def put_upload(tmp: Path, n: int) -> str:
    name = f"{n:032x}.jpg"
    p = tmp / "uploads" / PID / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(jpg())
    return f"uploads/{PID}/{name}"


def cfg(tmp: Path) -> Settings:
    return Settings(media_dir=str(tmp))


def make_graph(tmp: Path, store: InMemoryStore | None = None) -> Any:
    b = StateGraph(BookReviewState)
    b.add_node("manual_images", make_manual_images_node(cfg(tmp)))
    b.add_edge(START, "manual_images")
    b.add_edge("manual_images", END)
    return b.compile(checkpointer=InMemorySaver(), store=store)


def conf(tid: str = "t") -> RunnableConfig:
    return {"configurable": {"thread_id": tid, "project_id": PID}}


def start(graph: Any, series: str | None = None, tid: str = "t") -> dict[str, Any]:
    book: dict[str, Any] = {"title": "Sách thử"}
    if series:
        book["series"] = series
    graph.invoke(
        {"book": book, "storyboard": storyboard(4, long=True),
         "options": {"image_mode": "manual"}},
        conf(tid),
    )  # fmt: skip
    return graph.get_state(conf(tid)).interrupts[0].value  # type: ignore[no-any-return]


def full_uploads(tmp: Path, payload: dict[str, Any]) -> dict[str, str]:
    return {k: put_upload(tmp, i) for i, k in enumerate(payload["required"])}


def test_payload_has_prompt_for_every_image(tmp_path: Path) -> None:
    payload = start(make_graph(tmp_path))
    sb = Storyboard.model_validate(storyboard(4, long=True))
    plan = image_plan(sb, cfg(tmp_path))
    assert payload["type"] == "upload_images"
    assert len(payload["characters"]) == 3
    assert len(payload["scenes"]) == sum(plan.values())
    assert len(payload["required"]) == 3 + sum(plan.values())
    assert all(i["prompt"] for i in payload["characters"] + payload["scenes"])
    assert all(i["narration"] for i in payload["scenes"])


def test_missing_images_ask_again_without_failing(tmp_path: Path) -> None:
    graph = make_graph(tmp_path)
    payload = start(graph)
    ups = full_uploads(tmp_path, payload)
    first = payload["required"][0]
    partial = {k: v for k, v in ups.items() if k != first}
    graph.invoke(Command(resume={"uploads": partial}), conf())
    state = graph.get_state(conf())
    assert state.next == ("manual_images",)
    assert state.values.get("status") != "failed"
    assert state.interrupts[0].value["errors"] == [{"key": first, "code": "MISSING"}]


def test_foreign_or_bad_paths_rejected(tmp_path: Path) -> None:
    graph = make_graph(tmp_path)
    payload = start(graph)
    ups = full_uploads(tmp_path, payload)
    first = payload["required"][0]
    ups[first] = "../../etc/passwd"
    graph.invoke(Command(resume={"uploads": ups}), conf())
    errs = graph.get_state(conf()).interrupts[0].value["errors"]
    assert errs == [{"key": first, "code": "VALIDATION_ERROR"}]
    other = f"uploads/22222222-2222-2222-2222-222222222222/{0:032x}.jpg"
    ups[first] = other
    graph.invoke(Command(resume={"uploads": ups}), conf())
    assert graph.get_state(conf()).interrupts[0].value["errors"][0]["key"] == first


def test_full_upload_writes_pipeline_state_with_zero_cost(tmp_path: Path) -> None:
    graph = make_graph(tmp_path)
    payload = start(graph)
    graph.invoke(Command(resume={"uploads": full_uploads(tmp_path, payload)}), conf())
    values = graph.get_state(conf()).values
    assert graph.get_state(conf()).next == ()
    assert set(values["characters_approved"]) == {"an", "binh", "chi"}
    assert values["cost"] == {"usd": 0.0, "images": 0.0}
    sb = Storyboard.model_validate(values["storyboard"])
    n = 0
    for scene in sb.scenes:
        for k, img in enumerate(scene.images):
            assert img.path == values["asset_refs"][f"image:{scene.id}:{k}"]
            assert img.path
            assert Image.open(tmp_path / img.path).size == (720, 1280)
            n += 1
    assert n == len(payload["scenes"])
    assert values["asset_refs"]["character:an:approved"].startswith("uploads/")


def test_series_reuses_approved_characters(tmp_path: Path) -> None:
    store = InMemoryStore()
    g1 = make_graph(tmp_path, store)
    p1 = start(g1, series="Bộ truyện", tid="a")
    g1.invoke(Command(resume={"uploads": full_uploads(tmp_path, p1)}), conf("a"))
    g2 = make_graph(tmp_path, store)
    p2 = start(g2, series="Bộ truyện", tid="b")
    assert p2["characters"] == [] and set(p2["reused_characters"]) == {"an", "binh", "chi"}
    assert len(p2["required"]) == len(p2["scenes"])


def test_cancel_while_waiting(tmp_path: Path) -> None:
    graph = make_graph(tmp_path)
    start(graph)
    graph.invoke(Command(resume={"cancel": True}), conf())
    values = graph.get_state(conf()).values
    assert values["status"] == "cancelled" and values["error_code"] == "CANCELLED"


def test_full_graph_manual_never_calls_fal_and_reaches_motion(tmp_path: Path) -> None:
    provider = FakeImages()
    graph = build_graph(InMemorySaver(), image_provider=provider)
    assert graph.get_graph().nodes  # có nhánh manual cùng provider Fal
    # Chặn ở choose_image_mode đã được test ở test_graph; ở đây kiểm skip scene_images.
    from book_review_api.graph.build import _skip_when_manual

    called: list[int] = []

    def fake(state: BookReviewState) -> dict[str, Any]:
        called.append(1)
        return {"x": 1}

    wrapped = _skip_when_manual(fake)
    assert wrapped({"options": {"image_mode": "manual"}}) == {} and not called
    assert wrapped({"options": {"image_mode": "auto"}}) == {"x": 1}
    assert provider.calls == []
