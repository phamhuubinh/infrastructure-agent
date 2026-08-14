from __future__ import annotations

from dataclasses import replace

import pytest

from src.pipeline.semantic_plan import (
    SemanticPlan,
    TargetReference,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
    SemanticPlanValidationStatus,
    SemanticPlanValidationValue,
)


def test_status_and_reason_codes_are_typed_for_each_gate_outcome() -> None:
    plan = SemanticPlan()

    valid = SemanticPlanValidationResult.valid(plan)
    clarify = SemanticPlanValidationResult.clarify(
        plan, SemanticPlanValidationReason.TARGET_AMBIGUOUS
    )
    reject = SemanticPlanValidationResult.reject(
        SemanticPlanValidationReason.MUTATION_UNSAFE, plan=plan
    )
    unavailable = SemanticPlanValidationResult.unavailable(
        plan, SemanticPlanValidationReason.SOURCE_UNAVAILABLE
    )

    assert valid.status is SemanticPlanValidationStatus.VALID
    assert valid.can_execute
    assert clarify.reason is SemanticPlanValidationReason.TARGET_AMBIGUOUS
    assert reject.reason is SemanticPlanValidationReason.MUTATION_UNSAFE
    assert unavailable.status is SemanticPlanValidationStatus.UNAVAILABLE
    assert not unavailable.can_execute


def test_malformed_plan_can_be_rejected_without_a_plan_object() -> None:
    result = SemanticPlanValidationResult.reject(
        SemanticPlanValidationReason.MALFORMED_PLAN
    )

    assert result.original_plan is None
    assert result.validated_plan is None
    assert result.to_trace_dict()["reason"] == "malformed_plan"


def test_changed_plan_requires_explicit_original_and_normalized_trace_values() -> None:
    original = SemanticPlan(
        target=TargetReference(TargetReferenceKind.EXPLICIT, "MONITOR")
    )
    normalized = replace(
        original,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "monitor"),
    )

    with pytest.raises(ValueError, match="explicit trace values"):
        SemanticPlanValidationResult.valid(original, normalized_plan=normalized)

    value = SemanticPlanValidationValue.safe(
        "target", original="MONITOR", normalized="monitor"
    )
    result = SemanticPlanValidationResult.valid(
        original,
        normalized_plan=normalized,
        values=(value,),
    )

    assert result.original_plan is original
    assert result.validated_plan is normalized
    assert result.to_trace_dict()["values"] == [
        {"field": "target", "original": "MONITOR", "normalized": "monitor"}
    ]


def test_trace_values_are_bounded_and_redacted() -> None:
    value = SemanticPlanValidationValue.safe(
        "parameter.token",
        original="token=supersecret\n value",
        normalized="token=normalized",
    )

    trace = value.to_trace_dict()
    assert "supersecret" not in str(trace)
    assert "token=normalized" not in str(trace)
    assert "\n" not in str(trace)
