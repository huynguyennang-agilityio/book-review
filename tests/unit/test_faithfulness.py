"""faithfulness_eval (chấm, viết lại, gắn cờ), estimate_cost và payload của review_script."""

from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from book_review_api.config import Settings
from book_review_api.graph.build import build_graph
from book_review_api.rag.retrieve import Chunk
from book_review_api.storyboard.cost import estimate_media_cost
from book_review_api.storyboard.faithfulness import (
    ClaimVerdict,
    FaithfulnessChecker,
    Judgement,
    SceneRewrite,
    make_faithfulness_runner,
    scene_contexts,
)
from book_review_api.storyboard.schema import Citation, Scene, Storyboard

CHUNKS = {
    "c1": Chunk("c1", "Nhà giả kim của Paulo Coelho xuất bản năm 1988.", {"source_id": "s1"}),
    "c2": Chunk("c2", "Santiago là cậu bé chăn cừu.", {"source_id": "s1"}),
}


class FakeStructured:
    def __init__(self, owner: "Scripted", schema: type[BaseModel]) -> None:
        self.owner, self.schema = owner, schema

    def invoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        self.owner.calls.append((self.schema, messages))
        item = self.owner.script.pop(0)
        assert isinstance(item, self.schema), f"{type(item).__name__} != {self.schema.__name__}"
        raw = AIMessage(content="")
        raw.usage_metadata = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
        return {"raw": raw, "parsed": item, "parsing_error": None}


class Scripted(GenericFakeChatModel):
    script: list[Any] = []
    calls: list[Any] = []

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        return FakeStructured(self, schema)


def model(*script: Any) -> Scripted:
    return Scripted(messages=iter([]), script=list(script), calls=[])


def verdict(*supported: bool) -> Judgement:
    return Judgement(
        claims=[
            ClaimVerdict(claim=f"ý {i}", supported=s, reason="r") for i, s in enumerate(supported)
        ]
    )


def scene(sid: int, section: str = "body", narration: str = "Santiago chăn cừu.") -> Scene:
    cites = (
        [Citation(source_id="s1", chunk_id="c2", quote="cậu bé chăn cừu")]
        if section in ("context", "body")
        else []
    )
    return Scene(
        id=sid,
        section=section,  # type: ignore[arg-type]
        narration_vi=narration,
        citations=cites,
        scene_type="character",
        mood="warm",
    )


def storyboard(*scenes: Scene) -> Storyboard:
    return Storyboard(
        book={"title": "Nhà giả kim"},  # type: ignore[arg-type]
        book_category="fiction",
        spoiler_free=True,
        hook_vi="",
        characters=[{"name": "Santiago", "description_en": "boy"}],  # type: ignore[list-item]
        scenes=list(scenes),
        style_prompt_en="",
        caption_vi="",
    )


def checker(judge: Scripted, writer: Scripted) -> FaithfulnessChecker:
    return FaithfulnessChecker(judge, writer, Settings(), sleep=lambda _: None)


def test_score_is_share_of_supported_claims() -> None:
    assert verdict(True, True, False, True).score == 0.75
    assert verdict().score == 1.0  # không có khẳng định nào thì không có gì sai


def test_scene_contexts_are_cited_chunks_deduplicated() -> None:
    s = scene(1)
    s.citations.append(s.citations[0])
    assert scene_contexts(s, CHUNKS) == ["Santiago là cậu bé chăn cừu."]


def test_good_scene_is_not_rewritten() -> None:
    c = checker(model(verdict(True, True)), model())
    out, history = c.check_scene(scene(1), ["nguồn"])
    assert out.faithfulness == 1.0 and out.flags == [] and len(history) == 1


def test_low_scene_is_rewritten_with_source_only_instruction() -> None:
    writer = model(SceneRewrite(narration_vi="Santiago là cậu bé chăn cừu [1]."))
    c = checker(model(verdict(True, False), verdict(True)), writer)
    out, history = c.check_scene(scene(1, narration="Santiago chăn cừu ở Ai Cập."), ["nguồn"])
    assert [h.score for h in history] == [0.5, 1.0]
    assert out.narration_vi == "Santiago là cậu bé chăn cừu."
    assert out.citations == scene(1).citations  # vẫn bám đúng nguồn cũ
    assert out.flags == []
    prompt = writer.calls[0][1][-1].content
    assert "chỉ dùng thông tin trong nguồn" in prompt and "ý 1" in prompt


def test_scene_still_low_after_two_rounds_is_flagged() -> None:
    rewrite = SceneRewrite(narration_vi="vẫn bịa")
    judge = model(verdict(False), verdict(False), verdict(True, False))
    c = checker(judge, model(rewrite, rewrite))
    out, history = c.check_scene(scene(1), ["nguồn"])
    assert len(history) == 3  # chấm đầu + 2 vòng viết lại
    assert out.flags == ["LOW_FAITHFULNESS"]
    assert out.faithfulness == 0.5


def test_check_scores_only_context_and_body() -> None:
    sb = storyboard(scene(1, "hook", "Bạn có dám?"), scene(2, "context"), scene(3, "body"))
    c = checker(
        model(verdict(True), verdict(True, False), verdict(True)),
        model(SceneRewrite(narration_vi="x")),
    )
    out, scores = c.check(sb, CHUNKS)
    assert out.scenes[0].faithfulness is None
    assert scores["faithfulness"] == 1.0
    assert scores["faithfulness_initial"] == 0.75
    assert scores["scenes_scored"] == 2 and scores["scenes_rewritten"] == 1
    assert c.cost()["input_tokens"] == 400


def test_media_cost_counts_scene_and_character_images() -> None:
    sb = storyboard(scene(1, "hook", "abc"), scene(2, "body", "de"))
    cost = estimate_media_cost(sb, Settings(price_image_usd=0.03, i2v_clips=1))
    assert cost["images"] == 2 + 4  # 1 ảnh/cảnh + 4 ảnh sheet cho 1 nhân vật
    assert cost["tts_chars"] == 5
    assert cost["i2v_clips"] == 1
    assert round(cost["total_usd"], 4) == round(6 * 0.03 + 0.35, 4)
    assert cost["character_images"] == 4 and cost["scene_images"] == 2
    assert round(cost["manual_saving_usd"], 4) == round(6 * 0.03, 4)
    assert round(cost["manual_total_usd"], 4) == 0.35


def test_graph_scores_estimates_and_shows_everything_at_review() -> None:
    sb = storyboard(scene(1, "hook"), scene(2, "body"))
    research = {"book": {"title": "Nhà giả kim"}, "kind": "fiction"}
    judge = model(verdict(False), verdict(False), verdict(False))
    writer = model(SceneRewrite(narration_vi="a"), SceneRewrite(narration_vi="b"))
    graph = build_graph(
        InMemorySaver(),
        research_runner=lambda book: {"research": research},
        storyboard_runner=lambda _: {"storyboard": sb.model_dump(), "cost": {"usd": 0.01}},
        faithfulness_runner=make_faithfulness_runner(
            judge, writer, lambda ids: {i: CHUNKS[i] for i in ids}, Settings()
        ),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}
    graph.invoke({"book": {"title": "Nhà giả kim"}}, config)
    paused = graph.get_state(config)
    assert paused.next == ("review_script",)
    payload = paused.interrupts[0].value
    assert payload["low_faithfulness_scenes"] == [2]
    assert payload["storyboard"]["scenes"][1]["narration_vi"] == "b"
    assert payload["eval_scores"]["faithfulness"] == 0.0
    assert payload["sources"] == [{"source_id": "s1", "scene_ids": [2]}]
    assert payload["cost_estimate"]["images"] == 2 + 4
    assert payload["cost"]["usd"] > 0.01  # storyboard + giám khảo + viết lại
