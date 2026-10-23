"""Bộ kiểm tra hướng ảnh cảnh với model giả."""

import base64
import io
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from PIL import Image

from book_review_api.storyboard.orientation import CHECK_SIZE, make_orientation_checker


def jpg(w: int = 1088, h: int = 1920) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (120, 90, 60)).save(out, format="JPEG")
    return out.getvalue()


class FakeModel:
    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.messages: list[list[BaseMessage]] = []

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        outer = self

        class Runner:
            def invoke(self, messages: list[BaseMessage]) -> dict[str, Any]:
                outer.messages.append(messages)
                if outer.answer is None:
                    raise RuntimeError("503")
                raw = AIMessage(content="")
                raw.usage_metadata = {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11}
                return {
                    "raw": raw,
                    "parsed": schema(orientation=outer.answer),
                    "parsing_error": None,
                }

        return Runner()


def test_returns_model_answer_and_sends_small_image() -> None:
    model = FakeModel("rotated")
    check = make_orientation_checker(model, sleep=lambda _: None)  # type: ignore[arg-type]
    assert check(jpg()) == "rotated"
    content: Any = model.messages[0][0].content
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert img.size[0] <= CHECK_SIZE[0] and img.size[1] <= CHECK_SIZE[1]


def test_model_error_is_unsure() -> None:
    check = make_orientation_checker(FakeModel(None), sleep=lambda _: None)  # type: ignore[arg-type]
    assert check(jpg()) == "unsure"
