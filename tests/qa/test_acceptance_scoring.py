"""Canonical QA acceptance gate tests."""

from __future__ import annotations

from scripts.qa.acceptance_gates import (
    evaluate_acceptance_gates,
    runtime_summary,
)
from scripts.qa.report import (
    generate_standard_report,
)


def _report(
    *,
    elapsed_ms=50.0,
    tool_calls=2,
    model_calls=3,
    response_empty=False,
    mismatch_fields=None,
    quality=1.0,
):
    mismatch_fields = (
        mismatch_fields or []
    )

    mismatches = (
        [
            {
                "id": "fixture-case",
                "group": "A",
                "fields": (
                    mismatch_fields
                ),
            }
        ]
        if mismatch_fields
        else []
    )

    field_status = {
        "terminals": "match",
        "required_capability_sets": (
            "match"
        ),
        "required_capability_prefixes": (
            "match"
        ),
        "forbidden_capability_prefixes": (
            "match"
        ),
        "required_references": (
            "match"
        ),
        "forbidden_references": (
            "match"
        ),
        "min_successful_observations": (
            "match"
        ),
        "max_actions": "match",
        "approval_required": (
            "match"
        ),
        "failure": "match",
        "response_required": (
            "match"
        ),
    }

    for field in mismatch_fields:
        field_status[field] = (
            "mismatch"
        )

    return {
        "summary": {
            "strict_canonical_contract_rate": (
                quality
            ),
            "by_language": {
                "vi": {
                    "total": 1,
                    "passed": (
                        1
                        if quality == 1
                        else 0
                    ),
                    "strict_canonical_contract_rate": (
                        quality
                    ),
                }
            },
        },
        "diagnostics": {
            "behavioral_mismatches": (
                mismatches
            )
        },
        "cases": [
            {
                "id": "fixture-case",
                "elapsed_ms": (
                    elapsed_ms
                ),
                "response_empty": (
                    response_empty
                ),
                "response_character_count": 120,
                "field_status": (
                    field_status
                ),
                "actual": {
                    "runtime_metrics": {
                        "tool_calls": (
                            tool_calls
                        ),
                        "model_calls": (
                            model_calls
                        ),
                        "discovery_calls": 1,
                        "action_attempts": (
                            tool_calls
                        ),
                        "observation_count": (
                            tool_calls
                        ),
                    }
                },
            }
        ],
    }


def test_gate_passes_canonical_fixture():
    report = _report()

    result = (
        evaluate_acceptance_gates(
            report
        )
    )

    assert result.passed is True
    assert result.metrics[
        "runtime"
    ]["tool_calls"]["p95"] == 2.0
    assert result.metrics[
        "runtime"
    ]["model_calls"]["p95"] == 3.0
    assert result.metrics[
        "empty_response_count"
    ] == 0


def test_gate_rejects_contract_and_empty_response():
    report = _report(
        response_empty=True,
        mismatch_fields=[
            "terminals"
        ],
        quality=0.0,
    )

    result = (
        evaluate_acceptance_gates(
            report
        )
    )

    assert result.passed is False
    assert {
        violation.gate
        for violation
        in result.violations
    } == {
        "contract",
        "response",
    }


def test_safety_contract_mismatch_gets_safety_gate():
    report = _report(
        mismatch_fields=[
            "forbidden_references"
        ],
        quality=0.0,
    )

    result = (
        evaluate_acceptance_gates(
            report
        )
    )

    assert {
        violation.gate
        for violation
        in result.violations
    } == {
        "contract",
        "safety",
    }


def test_tool_budget_gate_uses_executed_actions():
    report = _report(
        tool_calls=13,
    )

    result = (
        evaluate_acceptance_gates(
            report,
            max_tool_calls_p95=12,
        )
    )

    assert any(
        violation.gate
        == "tool_budget"
        for violation
        in result.violations
    )


def test_model_budget_gate_uses_canonical_model_calls():
    report = _report(
        model_calls=9,
    )

    result = (
        evaluate_acceptance_gates(
            report,
            max_model_calls_p95=8,
        )
    )

    assert any(
        violation.gate
        == "model_budget"
        for violation
        in result.violations
    )


def test_latency_regression_requires_quality_improvement():
    baseline = _report(
        elapsed_ms=100,
        quality=0.8,
    )

    current = _report(
        elapsed_ms=111,
        quality=0.8,
    )

    result = (
        evaluate_acceptance_gates(
            current,
            baseline=baseline,
        )
    )

    assert any(
        violation.gate
        == "performance"
        for violation
        in result.violations
    )


def test_standard_report_keeps_canonical_summary():
    report = _report()

    payload, markdown = (
        generate_standard_report(
            report
        )
    )

    assert payload[
        "stage_summary"
    ][
        "strict_canonical_contract_rate"
    ] == 1.0

    assert payload[
        "acceptance"
    ]["passed"] is True

    assert (
        "Orion Acceptance Gates"
        in markdown
    )

    assert runtime_summary(
        report
    )["latency_ms"]["p95"] == 50.0
