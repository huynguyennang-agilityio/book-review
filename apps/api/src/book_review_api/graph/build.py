"""Graph `book_review` (mục 2.1 plan v5) với PostgresSaver và PostgresStore.

precheck → research_agent → identify_confirm → storyboard → faithfulness_eval
  → estimate_cost → review_script ✋
  → [tts_align → build_timeline → subtitles] ‖ [character_sheets → review_characters ✋
     (⟲ regen_characters) → scene_images]
  → motion → compose_render → save_memory
"""

from collections.abc import Callable, Sequence
from functools import wraps

from langchain_core.callbacks.manager import dispatch_custom_event
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from book_review_api.agents.research import ResearchRunner
from book_review_api.cancel import CancelFlags
from book_review_api.errors import ErrorCode
from book_review_api.graph.nodes.characters import (
    make_character_sheets_node,
    make_regen_characters_node,
)
from book_review_api.graph.nodes.common import NodeFn, NodeUpdate
from book_review_api.graph.nodes.faithfulness import (
    make_estimate_cost_node,
    make_faithfulness_node,
)
from book_review_api.graph.nodes.media import (
    make_build_timeline_node,
    make_compose_render_node,
    make_motion_node,
    make_scene_images_node,
    make_subtitles_node,
    make_tts_align_node,
)
from book_review_api.graph.nodes.precheck import precheck
from book_review_api.graph.nodes.research import identify_confirm, make_research_node
from book_review_api.graph.nodes.review import (
    SourceLookup,
    make_review_script,
    review_characters,
    review_script,
)
from book_review_api.graph.nodes.storyboard import make_storyboard_node
from book_review_api.graph.nodes.stubs import regen_characters_stub, save_memory, stub
from book_review_api.graph.state import TERMINAL_STATUSES, BookReviewState
from book_review_api.providers.image_fal import ImageProvider
from book_review_api.queue import JobRunner
from book_review_api.storyboard.faithfulness import FaithfulnessRunner
from book_review_api.storyboard.runner import StoryboardRunner

GRAPH_NAME = "book_review"

NODES: dict[str, NodeFn] = {
    "precheck": precheck,
    "research_agent": stub("research_agent"),
    "identify_confirm": identify_confirm,
    "storyboard": stub("storyboard"),
    "faithfulness_eval": stub("faithfulness_eval"),
    "estimate_cost": make_estimate_cost_node(),
    "review_script": review_script,
    "tts_align": stub("tts_align"),
    "build_timeline": stub("build_timeline"),
    "subtitles": stub("subtitles"),
    "character_sheets": stub("character_sheets"),
    "review_characters": review_characters,
    "scene_images": stub("scene_images"),
    "motion": stub("motion"),
    "compose_render": stub("compose_render"),
    "save_memory": save_memory,
}

# Cạnh có điều kiện: đi tiếp nếu graph chưa kết thúc, ngược lại về END.
_STEPS: list[tuple[str, Sequence[str]]] = [
    ("precheck", ["research_agent"]),
    ("research_agent", ["identify_confirm"]),
    ("identify_confirm", ["storyboard"]),
    ("storyboard", ["faithfulness_eval"]),
    ("faithfulness_eval", ["estimate_cost"]),
    ("estimate_cost", ["review_script"]),
    ("review_script", ["tts_align", "character_sheets"]),
    ("tts_align", ["build_timeline"]),
    ("build_timeline", ["subtitles"]),
    ("character_sheets", ["review_characters"]),
    ("regen_characters", ["review_characters"]),
    ("motion", ["compose_render"]),
    ("compose_render", ["save_memory"]),
]


NODE_EVENT = "node"


def _cancel_requested(flags: CancelFlags | None, state: BookReviewState) -> bool:
    """Cờ huỷ ở Redis (huỷ khi graph đang chạy). Cờ trong state do `node` tự kiểm."""
    if flags is None or state.get("status") in TERMINAL_STATUSES:
        return False
    thread_id = get_config().get("configurable", {}).get("thread_id")
    return bool(thread_id) and flags.is_set(str(thread_id))


def _announce(name: str, fn: NodeFn, flags: CancelFlags | None = None) -> NodeFn:
    """Báo tiến độ cho UI bằng event tuỳ biến `node` (phase start/end). Event STEP_* của adapter
    AG-UI bị lẫn tên bước nội bộ của research agent nên không đủ tin cậy để vẽ thanh tiến độ.

    Có `flags` thì kiểm cờ huỷ trước mỗi node: đã huỷ thì không chạy node (không tốn thêm tiền),
    ghi status `cancelled` rồi graph về END. Chi phí các node trước đó vẫn nằm trong state."""

    @wraps(fn)
    def wrapper(state: BookReviewState) -> NodeUpdate:
        if _cancel_requested(flags, state):
            return {"status": "cancelled", "error_code": ErrorCode.CANCELLED.value}
        dispatch_custom_event(NODE_EVENT, {"node": name, "phase": "start"})
        update = fn(state)
        dispatch_custom_event(NODE_EVENT, {"node": name, "phase": "end"})
        return update

    return wrapper


def _route(targets: Sequence[str]) -> Callable[[BookReviewState], list[str]]:
    def route(state: BookReviewState) -> list[str]:
        return [END] if state.get("status") in TERMINAL_STATUSES else list(targets)

    return route


def _after_characters(state: BookReviewState) -> list[str]:
    if state.get("status") in TERMINAL_STATUSES:
        return [END]
    return ["regen_characters"] if state.get("character_regen") else ["scene_images"]


def build_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
    research_runner: ResearchRunner | None = None,
    storyboard_runner: StoryboardRunner | None = None,
    faithfulness_runner: FaithfulnessRunner | None = None,
    job_runner: JobRunner | None = None,
    cancel_flags: CancelFlags | None = None,
    source_lookup: SourceLookup | None = None,
    image_provider: ImageProvider | None = None,
) -> CompiledStateGraph[BookReviewState]:
    """Runner (LLM, job worker) thiếu thì node tương ứng là node rỗng (test khung)."""
    nodes = {**NODES, "regen_characters": regen_characters_stub}
    if research_runner is not None:
        nodes["research_agent"] = make_research_node(research_runner)
    if storyboard_runner is not None:
        nodes["storyboard"] = make_storyboard_node(storyboard_runner)
    if faithfulness_runner is not None:
        nodes["faithfulness_eval"] = make_faithfulness_node(faithfulness_runner)
    if source_lookup is not None:
        nodes["review_script"] = make_review_script(source_lookup)
    if image_provider is not None:
        nodes["character_sheets"] = make_character_sheets_node(
            image_provider, cancel_flags=cancel_flags
        )
        nodes["regen_characters"] = make_regen_characters_node(
            image_provider, cancel_flags=cancel_flags
        )
    if job_runner is not None:
        nodes["tts_align"] = make_tts_align_node(job_runner)
        nodes["build_timeline"] = make_build_timeline_node(job_runner)
        nodes["subtitles"] = make_subtitles_node(job_runner)
        nodes["scene_images"] = make_scene_images_node(job_runner)
        nodes["motion"] = make_motion_node(job_runner)
        nodes["compose_render"] = make_compose_render_node(job_runner)
    builder = StateGraph(BookReviewState)
    for name, fn in nodes.items():
        builder.add_node(name, _announce(name, fn, cancel_flags))
    builder.add_edge(START, "precheck")
    for source, targets in _STEPS:
        builder.add_conditional_edges(source, _route(targets), [*targets, END])
    # Hợp hai nhánh: `motion` chờ cả phụ đề và ảnh cảnh. Nếu một nhánh đã huỷ thì `motion`
    # tự bỏ qua (xem `nodes.common.node`) rồi đi về END.
    # Sau khi duyệt nhân vật: có yêu cầu tạo lại thì quay về `regen_characters`, không thì đi tiếp.
    builder.add_conditional_edges(
        "review_characters", _after_characters, ["regen_characters", "scene_images", END]
    )
    builder.add_edge(["subtitles", "scene_images"], "motion")
    builder.add_edge("save_memory", END)
    return builder.compile(checkpointer=checkpointer, store=store, name=GRAPH_NAME)
