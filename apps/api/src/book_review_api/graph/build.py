"""Graph `book_review` (mục 2.1 plan v5) với PostgresSaver và PostgresStore.

precheck → research_agent → identify_confirm → storyboard → faithfulness_eval
  → estimate_cost → review_script ✋
  → [tts_align → build_timeline → subtitles] ‖ [character_sheets → review_characters ✋
     → scene_images]
  → motion → compose_render → save_memory
"""

from collections.abc import Callable, Sequence

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from book_review_api.agents.research import ResearchRunner
from book_review_api.graph.nodes.common import NodeFn
from book_review_api.graph.nodes.faithfulness import (
    make_estimate_cost_node,
    make_faithfulness_node,
)
from book_review_api.graph.nodes.media import make_build_timeline_node, make_tts_align_node
from book_review_api.graph.nodes.precheck import precheck
from book_review_api.graph.nodes.research import identify_confirm, make_research_node
from book_review_api.graph.nodes.review import review_characters, review_script
from book_review_api.graph.nodes.storyboard import make_storyboard_node
from book_review_api.graph.nodes.stubs import save_memory, stub
from book_review_api.graph.state import TERMINAL_STATUSES, BookReviewState
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
    ("review_characters", ["scene_images"]),
    ("motion", ["compose_render"]),
    ("compose_render", ["save_memory"]),
]


def _route(targets: Sequence[str]) -> Callable[[BookReviewState], list[str]]:
    def route(state: BookReviewState) -> list[str]:
        return [END] if state.get("status") in TERMINAL_STATUSES else list(targets)

    return route


def build_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
    research_runner: ResearchRunner | None = None,
    storyboard_runner: StoryboardRunner | None = None,
    faithfulness_runner: FaithfulnessRunner | None = None,
    job_runner: JobRunner | None = None,
) -> CompiledStateGraph[BookReviewState]:
    """Runner (LLM, job worker) thiếu thì node tương ứng là node rỗng (test khung)."""
    nodes = dict(NODES)
    if research_runner is not None:
        nodes["research_agent"] = make_research_node(research_runner)
    if storyboard_runner is not None:
        nodes["storyboard"] = make_storyboard_node(storyboard_runner)
    if faithfulness_runner is not None:
        nodes["faithfulness_eval"] = make_faithfulness_node(faithfulness_runner)
    if job_runner is not None:
        nodes["tts_align"] = make_tts_align_node(job_runner)
        nodes["build_timeline"] = make_build_timeline_node(job_runner)
    builder = StateGraph(BookReviewState)
    for name, fn in nodes.items():
        builder.add_node(name, fn)
    builder.add_edge(START, "precheck")
    for source, targets in _STEPS:
        builder.add_conditional_edges(source, _route(targets), [*targets, END])
    # Hợp hai nhánh: `motion` chờ cả phụ đề và ảnh cảnh. Nếu một nhánh đã huỷ thì `motion`
    # tự bỏ qua (xem `nodes.common.node`) rồi đi về END.
    builder.add_edge(["subtitles", "scene_images"], "motion")
    builder.add_edge("save_memory", END)
    return builder.compile(checkpointer=checkpointer, store=store, name=GRAPH_NAME)
