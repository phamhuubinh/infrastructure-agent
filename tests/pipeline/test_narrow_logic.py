from __future__ import annotations

from src.pipeline.narrow_logic import LogicOutcome, evaluate, evaluate_text


def test_narrow_logic_direct_universal_and_unknown_cases() -> None:
    assert evaluate(("All servers in the cluster are linux",), "Server A is running linux") is LogicOutcome.ENTAILED
    assert evaluate(("All servers in the cluster are linux",), "Server A is not running linux") is LogicOutcome.CONTRADICTED
    assert evaluate(("CPU usage of server A is constant",), "Server A has high memory usage") is LogicOutcome.NOT_ENOUGH_INFORMATION


def test_narrow_logic_text_is_explicit_and_abstains_on_unsupported_shapes() -> None:
    assert evaluate_text("Premises: All servers in the cluster are linux; Conclusion: Server A is running linux") is LogicOutcome.ENTAILED
    assert evaluate_text("Premise: ambiguous; therefore maybe true") is None
