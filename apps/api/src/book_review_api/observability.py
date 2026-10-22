"""Che PII trong log và trong trace gửi lên LangSmith (ngày 20)."""

import logging
from typing import Any

from langsmith import run_trees

from book_review_api.rag.pii import mask_pii


def mask_value(value: Any) -> Any:
    """Che email, số điện thoại, số thẻ trong mọi chuỗi của dict/list lồng nhau."""
    if isinstance(value, str):
        return mask_pii(value).text
    if isinstance(value, dict):
        return {k: mask_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(mask_value(v) for v in value)
    return value


def _mask_payload(payload: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = mask_value(payload)
    return masked


class PiiLogFilter(logging.Filter):
    """Che PII trong thông điệp log (đã định dạng cả đối số) trước khi ghi ra handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_pii(record.getMessage()).text
        record.args = None
        return True


def install_log_filter() -> None:
    """Gắn filter vào handler của root logger (filter gắn vào logger không áp cho logger con)."""
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, PiiLogFilter) for f in handler.filters):
            handler.addFilter(PiiLogFilter())


def setup_tracing() -> None:
    """Tạo sẵn client LangSmith dùng chung với hàm che đầu vào/đầu ra. Gọi một lần lúc khởi động,
    trước khi có run nào được ghi (client được cache nên lần gọi sau không đổi cấu hình)."""
    run_trees.get_cached_client(hide_inputs=_mask_payload, hide_outputs=_mask_payload)
