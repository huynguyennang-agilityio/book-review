import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_eval_gate", Path(__file__).resolve().parents[2] / "scripts" / "check_eval_gate.py"
)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _report(score: float, failed: list[str] | None = None) -> dict[str, object]:
    return {"summary": {"context_body": {"vi": score, "vi_final": score}}, "books_failed": failed}


def test_gate_passes_at_threshold() -> None:
    assert gate.check(_report(0.93), 0.9)[0]


def test_gate_fails_below_threshold() -> None:
    assert not gate.check(_report(0.85), 0.9)[0]


def test_gate_fails_when_a_book_failed() -> None:
    assert not gate.check(_report(0.99, ["sapiens"]), 0.9)[0]
