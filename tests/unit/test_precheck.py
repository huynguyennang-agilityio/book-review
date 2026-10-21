import pytest

from book_review_api.graph.nodes.precheck import find_excluded_keyword, fold, precheck


def test_fold() -> None:
    assert fold("  Kiếm   HIỆP Đông Á ") == "kiem hiep dong a"


@pytest.mark.parametrize(
    "title",
    [
        "Tuyển tập truyện kiếm hiệp",
        "TIÊN HIỆP kỳ duyên",
        "tien hiep ky duyen",
        "Huyền huyễn thế giới",
        "Hành trình tu tiên",
        "Võ hiệp Cổ Long",
        "Thiên Long Bát Bộ",
        "Phàm nhân tu tiên truyện",
        "Kiếm-hiệp: tập 1",
    ],
)
def test_excluded(title: str) -> None:
    assert find_excluded_keyword(title) is not None


@pytest.mark.parametrize(
    "title",
    [
        "Nhà giả kim",
        "Đắc nhân tâm",
        "Tự tin để thành công",
        "Sapiens: Lược sử loài người",
    ],
)
def test_allowed(title: str) -> None:
    assert find_excluded_keyword(title) is None


def test_word_boundary() -> None:
    # "tu tiên" không khớp giữa chữ khác.
    assert find_excluded_keyword("Bút tu tiênz") is None


def test_precheck_node() -> None:
    assert precheck({"book": {"title": "Nhà giả kim"}})["status"] == "running"
    rejected = precheck({"book": {"title": "Truyện kiếm hiệp"}})
    assert rejected == {"status": "rejected", "error_code": "GENRE_EXCLUDED"}
