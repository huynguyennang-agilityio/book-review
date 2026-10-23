"""Chia bài review thành cảnh giữ nguyên văn và chuẩn hoá cho TTS (tab review có sẵn, ngày 3)."""

import pytest

from book_review_api.storyboard.duration import count_syllables, estimate_seconds, scene_seconds
from book_review_api.storyboard.verbatim import (
    MAX_SYLLABLES,
    normalize_for_tts,
    paragraphs,
    read_number,
    split_review_into_scenes,
    split_sentences,
    strip_markdown,
    verbatim_problems,
)

SENTENCES = [
    "Nhà giả kim kể về Santiago, một cậu bé chăn cừu ở vùng Andalusia.",
    "Cậu nhiều lần mơ thấy kho báu nằm gần kim tự tháp Ai Cập.",
    "Cậu bán đàn cừu và lên đường đi tìm giấc mơ của mình.",
    "Trên đường đi, cậu gặp một ông vua già, một người Anh và một nhà giả kim.",
    "Mỗi người dạy cậu một điều về vận mệnh và ngôn ngữ của thế giới!",
    "Liệu cậu có tìm thấy kho báu không?",
    "Câu trả lời nằm ở chính nơi cậu đã bắt đầu.",
]


def long_main(syllables: int) -> str:
    """Nhiều đoạn văn, tổng khoảng `syllables` âm tiết."""
    out: list[str] = []
    total = 0
    i = 0
    while total < syllables:
        s = SENTENCES[i % len(SENTENCES)]
        out.append(s)
        total += count_syllables(s)
        i += 1
    # Ba câu một đoạn.
    return "\n\n".join(" ".join(out[k : k + 3]) for k in range(0, len(out), 3))


# --- Đọc số và ký hiệu ----------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "không"),
        (5, "năm"),
        (10, "mười"),
        (15, "mười lăm"),
        (21, "hai mươi mốt"),
        (105, "một trăm linh năm"),
        (1005, "một nghìn không trăm linh năm"),
        (1200, "một nghìn hai trăm"),
        (1988, "một nghìn chín trăm tám mươi tám"),
        (1_200_500, "một triệu hai trăm nghìn năm trăm"),
        (3_000_000_000, "ba tỷ"),
    ],
)
def test_read_number(n: int, words: str) -> None:
    assert read_number(n) == words


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("Có 3 bài học.", "Có ba bài học."),
        ("Bán 1.200 bản", "Bán một nghìn hai trăm bản"),
        ("tăng 15% mỗi năm", "tăng mười lăm phần trăm mỗi năm"),
        ("gấp 2,5 lần", "gấp hai phẩy năm lần"),
        ("đứng thứ 4", "đứng thứ tư"),
        ("Tom & Jerry", "Tom và Jerry"),
        ("NXB Trẻ, TS. Lan", "nhà xuất bản Trẻ, tiến sĩ Lan"),
        ("Không có số nào.", "Không có số nào."),
    ],
)
def test_normalize_for_tts(text: str, spoken: str) -> None:
    assert normalize_for_tts(text).text == spoken


def test_normalize_lists_changes_for_review_screen() -> None:
    out = normalize_for_tts("Năm 1988 có 15% người đọc.")
    assert {"from": "1988", "to": "một nghìn chín trăm tám mươi tám"} in out.changes
    assert {"from": "15%", "to": "mười lăm phần trăm"} in out.changes
    assert normalize_for_tts("Không đổi gì.").changes == []


# --- Markdown, tách câu ---------------------------------------------------------


def test_strip_markdown() -> None:
    md = "## Tiêu đề\n- **Đậm** và *nghiêng*, [liên kết](https://x.vn) và `mã`\n> Trích\n---"
    assert strip_markdown(md) == "Tiêu đề\nĐậm và nghiêng, liên kết và mã\nTrích"
    assert strip_markdown("Văn bản thường, không đổi.") == "Văn bản thường, không đổi."


def test_split_sentences_keeps_abbreviations_and_quotes() -> None:
    text = 'J. K. Rowling viết truyện. TS. Lan nói: "Hay quá!" Rồi sao? Hết…'
    assert split_sentences(text) == [
        "J. K. Rowling viết truyện.",
        'TS. Lan nói: "Hay quá!"',
        "Rồi sao?",
        "Hết…",
    ]


# --- Chia cảnh ------------------------------------------------------------------


def test_only_main_gives_body_scenes() -> None:
    main = long_main(150)
    scenes = split_review_into_scenes(None, main, None)
    assert {s.section for s in scenes} == {"body"}
    assert not verbatim_problems(None, main, None, scenes)


def test_all_three_fields() -> None:
    main = long_main(150)
    scenes = split_review_into_scenes(
        "Bạn có dám đi theo giấc mơ?\nHãy nghe câu chuyện này.", main, "Sách hay. Nên đọc."
    )
    sections = [s.section for s in scenes]
    assert sections[0] == "hook" and sections.count("hook") == 1
    assert sections[-1] == "review_cta"
    # Hook nhiều dòng vẫn là đúng 1 cảnh.
    assert scenes[0].text == "Bạn có dám đi theo giấc mơ? Hãy nghe câu chuyện này."
    assert sections == sorted(sections, key=["hook", "body", "review_cta"].index)


@pytest.mark.parametrize(("hook", "comment"), [("", "Nên đọc."), ("Mở đầu.", None), (None, "")])
def test_empty_fields_have_no_scenes(hook: str | None, comment: str | None) -> None:
    scenes = split_review_into_scenes(hook, long_main(120), comment)
    assert ("hook" in {s.section for s in scenes}) == bool(hook)
    assert ("review_cta" in {s.section for s in scenes}) == bool(comment)


def test_scenes_do_not_cross_paragraphs() -> None:
    main = "Đoạn một ngắn.\n\nĐoạn hai cũng ngắn."
    texts = [s.text for s in split_review_into_scenes(None, main, None)]
    assert texts == ["Đoạn một ngắn.", "Đoạn hai cũng ngắn."]


def test_concatenation_equals_source() -> None:
    hook = "Có **3** lý do để đọc cuốn sách này."
    main = "## Nội dung\n" + long_main(300) + "\n- Năm 1988, sách bán 1.200 bản, tăng 15%."
    comment = "Mình chấm 9/10. Bạn nên đọc!"
    scenes = split_review_into_scenes(hook, main, comment)
    assert verbatim_problems(hook, main, comment, scenes) == []
    body = " ".join(s.text for s in scenes if s.section == "body")
    assert body == " ".join(paragraphs(main))
    assert "một nghìn hai trăm" in " ".join(s.narration for s in scenes)


def test_verbatim_check_catches_lost_or_swapped_sentences() -> None:
    main = long_main(150)
    scenes = split_review_into_scenes(None, main, None)
    assert verbatim_problems(None, main, None, scenes[1:])
    assert verbatim_problems(None, main, None, [scenes[1], scenes[0], *scenes[2:]])


def test_450_words_length_and_scene_size() -> None:
    main = long_main(450)
    scenes = split_review_into_scenes(None, main, None)
    seconds = estimate_seconds(s.narration for s in scenes)
    # ~3,8 âm tiết/giây: 450 âm tiết đọc ~2 phút, mỗi cảnh ~7 giây.
    assert 16 <= len(scenes) <= 22
    assert 110 <= seconds <= 140
    assert all(scene_seconds(s.narration) <= 12 for s in scenes)


def test_long_sentence_is_split_at_commas() -> None:
    clause = "cậu đi qua sa mạc rộng lớn với đoàn lữ hành"
    sentence = ", ".join([clause] * 6) + "."
    assert count_syllables(sentence) > MAX_SYLLABLES
    scenes = split_review_into_scenes(None, sentence, None)
    assert len(scenes) > 1
    assert not verbatim_problems(None, sentence, None, scenes)
