"""Model viết kịch bản (OpenAI/Gemini) và tiền theo từng model."""

import pytest
from langchain_core.messages import AIMessage

from book_review_api.config import Settings
from book_review_api.providers.llm_writer import make_writer_model, writer_uses_openai
from book_review_api.providers.structured import Usage


def msg(model: str, n_in: int, n_out: int) -> AIMessage:
    return AIMessage(
        "x",
        usage_metadata={"input_tokens": n_in, "output_tokens": n_out, "total_tokens": n_in + n_out},
        response_metadata={"model_name": model},
    )


def test_auto_uses_openai_only_with_key() -> None:
    assert not writer_uses_openai(Settings(writer_provider="auto", openai_api_key=""))
    assert writer_uses_openai(Settings(writer_provider="auto", openai_api_key="sk-test"))
    assert not writer_uses_openai(Settings(writer_provider="gemini", openai_api_key="sk-test"))
    with pytest.raises(RuntimeError):
        writer_uses_openai(Settings(writer_provider="openai", openai_api_key=""))


def test_make_writer_model_picks_provider() -> None:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_openai import ChatOpenAI

    s = Settings(google_api_key="g", openai_api_key="sk-test", writer_model="gpt-5.4-mini")
    model = make_writer_model(s)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-5.4-mini"
    gem = make_writer_model(Settings(google_api_key="g", openai_api_key=""))
    assert isinstance(gem, ChatGoogleGenerativeAI)


def test_price_for_matches_versioned_names_and_falls_back() -> None:
    s = Settings(price_input_per_mtok=0.3, price_output_per_mtok=2.5)
    assert s.price_for("gpt-5.4-mini-2026-03-17") == (0.75, 4.50)
    assert s.price_for("gpt-5-mini") == (0.25, 2.00)
    assert s.price_for("models/gemini-3.5-flash-lite") == (0.3, 2.5)
    assert s.price_for("") == (0.3, 2.5)


def test_usage_charges_each_model_at_its_price() -> None:
    s = Settings(price_input_per_mtok=0.3, price_output_per_mtok=2.5)
    u = Usage()
    u.add(msg("gpt-5.4-mini-2026-03-17", 1_000_000, 100_000))
    u.add(msg("gemini-3.5-flash-lite", 1_000_000, 0))
    assert u.input_tokens == 2_000_000
    assert u.usd_for(s) == pytest.approx(0.75 + 0.45 + 0.3)
