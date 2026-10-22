"""Chữ nổi bật theo timeline và sources.md của node compose_render (ngày 19)."""

from typing import Any

from book_review_api.graph.nodes.media import highlights_for, sources_markdown

STORYBOARD: dict[str, Any] = {
    "book": {"title": "Nhà giả kim"},
    "hook_vi": "Bạn dám theo giấc mơ?",
    "scenes": [
        {"id": 1, "section": "hook", "on_screen_text_vi": "x"},
        {"id": 2, "section": "body", "on_screen_text_vi": "Chương 1"},
        {
            "id": 3,
            "section": "body",
            "citations": [{"source_id": "s1", "chunk_id": "c1", "quote": "một câu"}],
        },
    ],
}
TIMELINE: dict[str, Any] = {
    "scenes": [
        {"scene_id": 1, "start_s": 0.0, "end_s": 8.0},
        {"scene_id": 2, "start_s": 8.2, "end_s": 9.0},
        {"scene_id": 3, "start_s": 9.2, "end_s": 15.0},
    ]
}


def test_highlights_follow_timeline() -> None:
    assert highlights_for(STORYBOARD, TIMELINE) == [
        {"text": "Bạn dám theo giấc mơ?", "start_s": 0.0, "end_s": 5.0},
        {"text": "Chương 1", "start_s": 8.2, "end_s": 9.0},
    ]


def test_sources_markdown_lists_citations_by_scene() -> None:
    md = sources_markdown(STORYBOARD, {"s1": {"title": "Wikipedia", "url": "https://x.vn"}})
    assert "[Wikipedia](https://x.vn)" in md
    assert "### Cảnh 3 (body)" in md and '"một câu"' in md
    assert "không có trích dẫn" in sources_markdown({"scenes": []}, {})
