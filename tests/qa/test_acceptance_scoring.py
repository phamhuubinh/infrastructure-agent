"""DR1-807/808/810 — stage acceptance, budget and dashboard contracts."""

from __future__ import annotations

from scripts.qa.acceptance_gates import evaluate_acceptance_gates, runtime_summary
from scripts.qa.report import generate_standard_report


def _report(
    *,
    elapsed_ms: float = 50.0,
    tool_calls: int = 2,
    inspections: int = 2,
    response_empty: bool = False,
    mismatches: list[dict] | None = None,
    accuracy: float = 1.0,
) -> dict:
    return {
        "summary": {
            "strict_correct_investigation_rate": accuracy,
            "observable_core_accuracy": accuracy,
            "by_language": {
                "vi": {"total": 1, "strict_correct_investigation_rate": accuracy}
            },
        },
        "diagnostics": {"behavioral_mismatches": mismatches or []},
        "cases": [
            {
                "id": "fixture-case",
                "elapsed_ms": elapsed_ms,
                "response_empty": response_empty,
                "actual": {
                    "runtime_metrics": {
                        "tool_calls": tool_calls,
                        "parallel_ratio": 1.0,
                        "expansion_rounds": 0,
                        "security_inspections_total": inspections,
                    },
                    "response_metrics": {
                        "character_count": 120,
                        "estimated_output_tokens": 30,
                    },
                },
            }
        ],
    }


def test_stage_gate_passes_reviewed_fixture_and_reports_runtime_metrics() -> None:
    report = _report()

    result = evaluate_acceptance_gates(report)

    assert result.passed is True
    assert result.metrics["runtime"]["tool_calls"]["p95"] == 2.0
    assert result.metrics["runtime"]["parallel_ratio"]["median"] == 1.0
    assert result.metrics["runtime"]["response_characters"]["p95"] == 120.0
    assert result.metrics["runtime"]["estimated_output_tokens"]["median"] == 30.0
    assert result.metrics["empty_response_count"] == 0


def test_stage_gate_rejects_accuracy_empty_response_and_missing_security_receipt() -> (
    None
):
    report = _report(
        inspections=0,
        response_empty=True,
        mismatches=[{"id": "routing-regression"}],
    )

    result = evaluate_acceptance_gates(report)

    assert result.passed is False
    assert {violation.gate for violation in result.violations} == {
        "accuracy",
        "response",
        "safety",
    }


def test_latency_regression_fails_when_accuracy_does_not_improve() -> None:
    baseline = _report(elapsed_ms=100, accuracy=0.8)
    current = _report(elapsed_ms=111, accuracy=0.8)

    result = evaluate_acceptance_gates(current, baseline=baseline)

    assert any(violation.gate == "performance" for violation in result.violations)


def test_standard_dashboard_keeps_stage_language_and_acceptance_sections() -> None:
    report = _report()

    payload, markdown = generate_standard_report(report)

    assert payload["stage_summary"]["by_language"]["vi"]["total"] == 1
    assert payload["acceptance"]["passed"] is True
    assert "Orion Acceptance Gates" in markdown
    assert runtime_summary(report)["latency_ms"]["p95"] == 50.0
