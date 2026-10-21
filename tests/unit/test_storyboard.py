"""Storyboard: validator citation, writer với model giả, node trong graph."""

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from book_review_api.config import Settings
from book_review_api.graph.build import build_graph
from book_review_api.rag.golden import load_golden
from book_review_api.rag.retrieve import Chunk
from book_review_api.storyboard.runner import make_storyboard_runner
from book_review_api.storyboard.schema import Citation, Scene, Storyboard
from book_review_api.storyboard.validate import scene_problems, storyboard_problems
from book_review_api.storyboard.writer import (
    CitationDraft,
    Outline,
    OutlineSection,
    SceneDraft,
    SectionDraft,
    StoryboardError,
    StoryboardWriter,
)

GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden"
CHUNK = Chunk(
    "c1",
    "Nhà giả kim là tiểu thuyết của Paulo Coelho,   xuất bản năm 1988.",
    {"source_id": "s1"},
)


def scene(section: str = "body", cites: list[Citation] | None = None) -> Scene:
    return Scene(
        id=1,
        section=section,  # type: ignore[arg-type]
        narration_vi="x",
        citations=cites or [],
        scene_type="title",
        mood="warm",
    )


def cite(quote: str, chunk_id: str = "c1", source_id: str = "s1") -> Citation:
    return Citation(source_id=source_id, chunk_id=chunk_id, quote=quote)


# --- Validator ------------------------------------------------------------------


def test_body_scene_without_citation_is_invalid() -> None:
    assert scene_problems(scene("body"), {"c1": CHUNK})
    assert scene_problems(scene("context"), {"c1": CHUNK})


def test_hook_and_cta_do_not_need_citation() -> None:
    assert scene_problems(scene("hook"), {"c1": CHUNK}) == []
    assert scene_problems(scene("review_cta"), {"c1": CHUNK}) == []


def test_valid_quote_matches_despite_case_and_whitespace() -> None:
    s = scene(cites=[cite("PAULO COELHO, xuất bản năm 1988")])
    assert scene_problems(s, {"c1": CHUNK}) == []


@pytest.mark.parametrize(
    "citation",
    [
        cite("Paulo Coelho viết năm 1990"),  # quote không có trong chunk
        cite("Paulo Coelho", chunk_id="zzz"),  # chunk không tồn tại
        cite("Paulo Coelho", source_id="other"),  # source không khớp chunk
        cite("   "),  # quote trống
    ],
)
def test_bad_citation_is_reported(citation: Citation) -> None:
    assert scene_problems(scene(cites=[citation]), {"c1": CHUNK})


def test_quote_over_200_chars_is_rejected_even_if_present() -> None:
    long_text = "từ " * 100
    chunk = Chunk("c1", long_text, {"source_id": "s1"})
    problems = scene_problems(scene(cites=[cite(long_text.strip())]), {"c1": chunk})
    assert any("200" in p for p in problems)


def test_duplicate_scene_ids_reported() -> None:
    s = scene("hook")
    sb = Storyboard(
        book={"title": "X"},  # type: ignore[arg-type]
        book_category="fiction",
        spoiler_free=True,
        hook_vi="",
        scenes=[s, s],
        style_prompt_en="",
        caption_vi="",
    )
    assert any("trùng" in p for p in storyboard_problems(sb, {}))


# --- Writer với model giả -------------------------------------------------------


class FakeStructured:
    def __init__(self, owner: "ScriptedStructuredModel", schema: type[BaseModel]) -> None:
        self.owner, self.schema = owner, schema

    def invoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
        self.owner.calls.append((self.schema, messages))
        item = self.owner.script.pop(0)
        assert isinstance(item, self.schema), f"{type(item).__name__} != {self.schema.__name__}"
        raw = AIMessage(content="")
        raw.usage_metadata = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
        return {"raw": raw, "parsed": item, "parsing_error": None}


class ScriptedStructuredModel(GenericFakeChatModel):
    script: list[Any] = []
    calls: list[Any] = []

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        return FakeStructured(self, schema)


def fixed_retriever(chunks: list[Chunk]) -> Any:
    return lambda _query: chunks


def outline() -> Outline:
    return Outline(
        style_prompt_en="watercolor",
        caption_vi="cap",
        hashtags=["#sach"],
        sections=[
            OutlineSection(section="hook", brief="mở", queries=["tổng quan"]),
            OutlineSection(section="context", brief="bối cảnh", queries=["tác giả năm xuất bản"]),
            OutlineSection(section="body", brief="nội dung", queries=["Santiago kho báu"]),
            OutlineSection(section="review_cta", brief="kết", queries=["bài học"]),
        ],
    )


def draft(passage: int = 1, quote: str = "Paulo Coelho", cited: bool = True) -> SectionDraft:
    cites = [CitationDraft(passage=passage, quote=quote)] if cited else []
    return SectionDraft(
        scenes=[SceneDraft(narration_vi="n", scene_type="title", mood="warm", citations=cites)]
    )


def make_writer(script: list[Any], **settings: Any) -> tuple[StoryboardWriter, Any]:
    book = next(b for b in load_golden(GOLDEN) if b.slug == "nha-gia-kim")
    model = ScriptedStructuredModel(messages=iter([]), script=script, calls=[])
    retriever = fixed_retriever(book.chunks()[:1])
    sleeps: list[float] = []
    w = StoryboardWriter(model, retriever, Settings(**settings), sleep=sleeps.append)
    return w, model


BOOK: dict[str, Any] = {"title": "Nhà giả kim", "author": "Paulo Coelho", "year": 1988}


def test_writer_builds_storyboard_with_resolved_citations() -> None:
    w, _ = make_writer([outline(), draft(cited=False), draft(), draft(), draft(cited=False)])
    sb = w.write(w_book(), "fiction")
    assert [s.section for s in sb.scenes] == ["hook", "context", "body", "review_cta"]
    assert [s.id for s in sb.scenes] == [1, 2, 3, 4]
    body = sb.scenes[2]
    assert body.citations[0].chunk_id.startswith("nha-gia-kim/")
    assert body.citations[0].source_id.startswith("nha-gia-kim/")
    assert sb.hook_vi == sb.scenes[0].narration_vi
    assert sb.prompt_version == "storyboard_v1"
    assert w.usage.input_tokens == 500


def w_book() -> Any:
    from book_review_api.storyboard.schema import BookIdentity

    return BookIdentity.model_validate(BOOK)


def test_writer_retries_section_with_validator_feedback() -> None:
    bad = draft(quote="câu không có trong nguồn")
    w, model = make_writer(
        [outline(), draft(cited=False), bad, draft(), draft(), draft(cited=False)]
    )
    sb = w.write(w_book(), "fiction")
    assert len(sb.scenes) == 4
    retry_messages = model.calls[3][1]  # lần gọi thứ 2 của phần context
    assert "quote không có nguyên văn" in retry_messages[-1].content


def test_writer_gives_up_after_retries() -> None:
    def bad() -> SectionDraft:
        return draft(quote="không có thật")

    w, _ = make_writer([outline(), draft(cited=False), bad(), bad(), bad()])
    with pytest.raises(StoryboardError) as err:
        w.write(w_book(), "fiction")
    assert err.value.problems


def test_writer_rejects_unknown_passage_number() -> None:
    w, _ = make_writer([outline(), draft(cited=False), draft(passage=99)] * 3)
    with pytest.raises(StoryboardError):
        w.write(w_book(), "fiction")


def test_non_fiction_has_no_characters() -> None:
    o = outline()
    o.characters = [{"name": "A", "description_en": "tall"}]  # type: ignore[list-item]
    w, _ = make_writer([o, draft(cited=False), draft(), draft(), draft(cited=False)])
    assert w.write(w_book(), "non_fiction").characters == []


def test_missing_outline_section_fails() -> None:
    o = outline()
    o.sections = o.sections[:3]
    w, _ = make_writer([o])
    with pytest.raises(StoryboardError):
        w.write(w_book(), "fiction")


def test_model_error_is_retried_with_backoff() -> None:
    class Flaky(ScriptedStructuredModel):
        fails: int = 2

        def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
            inner = super().with_structured_output(schema)
            outer = self

            class Wrapper:
                def invoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
                    if outer.fails:
                        outer.fails -= 1
                        raise RuntimeError("429")
                    return inner.invoke(messages)  # type: ignore[no-any-return]

            return Wrapper()

    book = next(b for b in load_golden(GOLDEN) if b.slug == "nha-gia-kim")
    sleeps: list[float] = []
    model = Flaky(messages=iter([]), script=[outline()], calls=[])
    w = StoryboardWriter(model, fixed_retriever(book.chunks()[:1]), Settings(), sleep=sleeps.append)
    w.outline(w_book(), "fiction", [])
    assert sleeps == [15.0, 30.0]


# --- Runner và graph ------------------------------------------------------------


def runner_for(script: list[Any]) -> Any:
    book = next(b for b in load_golden(GOLDEN) if b.slug == "nha-gia-kim")
    model = ScriptedStructuredModel(messages=iter([]), script=script, calls=[])
    return make_storyboard_runner(model, fixed_retriever(book.chunks()[:1]), Settings())


RESEARCH = {"book": BOOK, "kind": "fiction"}


def test_runner_returns_storyboard_and_cost() -> None:
    out = runner_for([outline(), draft(cited=False), draft(), draft(), draft(cited=False)])(
        RESEARCH
    )
    assert out["storyboard"]["scenes"][2]["citations"]
    assert out["cost"]["input_tokens"] == 500
    assert out["cost"]["usd"] > 0
    assert "status" not in out


def test_runner_fails_with_low_faithfulness_when_citations_stay_invalid() -> None:
    def bad() -> SectionDraft:
        return draft(quote="bịa")

    out = runner_for([outline(), draft(cited=False), bad(), bad(), bad()])(RESEARCH)
    assert out["status"] == "failed"
    assert out["error_code"] == "LOW_FAITHFULNESS"
    assert "storyboard" not in out


def test_graph_runs_storyboard_node_after_research() -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    graph = build_graph(
        InMemorySaver(),
        research_runner=lambda book: {"research": {**RESEARCH, "book": book}},
        storyboard_runner=runner_for(
            [outline(), draft(cited=False), draft(), draft(), draft(cited=False)]
        ),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}
    state = graph.invoke({"book": {"title": "Nhà giả kim"}}, config)
    assert state["storyboard"]["book"]["title"] == "Nhà giả kim"


def test_trim_quote_cuts_at_word_boundary_and_stays_a_substring() -> None:
    from book_review_api.storyboard.writer import trim_quote

    text = " ".join(f"từ{i}" for i in range(80))
    out = trim_quote(text)
    assert len(out) <= 200
    assert text.startswith(out)
    assert not out.endswith(" ")
    assert trim_quote("  ngắn  ") == "ngắn"


def test_writer_drops_uncited_scenes_in_cited_sections() -> None:
    mixed = SectionDraft(
        scenes=[
            SceneDraft(narration_vi="không nguồn", scene_type="title", mood="m"),
            SceneDraft(
                narration_vi="có nguồn",
                scene_type="title",
                mood="m",
                citations=[CitationDraft(passage=1, quote="Paulo Coelho")],
            ),
        ]
    )
    w, _ = make_writer([outline(), draft(cited=False), mixed, draft(), draft(cited=False)])
    sb = w.write(w_book(), "fiction")
    assert [s.narration_vi for s in sb.scenes if s.section == "context"] == ["có nguồn"]
    assert [s.id for s in sb.scenes] == [1, 2, 3, 4]
