"""Mask PII trong log và trace."""

import logging
from typing import Any

from book_review_api.observability import PiiLogFilter, mask_value

CARD = "4111 1111 1111 1111"


def test_mask_value_nested() -> None:
    data = {
        "inputs": {"messages": ["liên hệ a@b.com hoặc 0912 345 678", {"card": CARD}]},
        "n": 3,
        "pair": ("x@y.io", 1),
    }
    out = mask_value(data)
    assert out["inputs"]["messages"][0] == "liên hệ [EMAIL] hoặc [PHONE]"
    assert out["inputs"]["messages"][1] == {"card": "[CARD]"}
    assert out["n"] == 3
    assert out["pair"] == ("[EMAIL]", 1)


def test_log_filter_masks_message_and_args() -> None:
    record = logging.LogRecord("t", logging.INFO, "f", 1, "gửi tới %s", ("a@b.com",), None)
    assert PiiLogFilter().filter(record)
    assert record.getMessage() == "gửi tới [EMAIL]"


def test_tracing_client_hides_pii() -> None:
    from langsmith import run_trees

    from book_review_api.observability import setup_tracing

    setup_tracing()
    client = run_trees.get_cached_client()
    hide: Any = client._hide_inputs
    assert callable(hide)
    assert hide({"q": "a@b.com"}) == {"q": "[EMAIL]"}
