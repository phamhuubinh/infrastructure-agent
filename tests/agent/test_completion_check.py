from __future__ import annotations

from src.agent.completion_check import (
    CompletionCheck,
    CompletionCheckReason,
    CompletionCheckStatus,
)
from src.agent.controller_contracts import (
    AgentObservation,
    AgentObservationStatus,
    AgentRunState,
)
from src.pipeline.hard_request_constraints import (
    HardRequestConstraints,
    HardTargetReference,
)
from src.pipeline.request_semantics import SourceConstraint


def _fact(**values: object) -> dict[str, object]:
    return {"validity": "valid", "freshness": "fresh", **values}


def _observation(
    *,
    action_id: int = 1,
    capability_id: str = "host.get_cpu",
    status: AgentObservationStatus = AgentObservationStatus.SUCCESS,
    facts: tuple[dict[str, object], ...] = (),
    target_id: str | None = None,
    source_id: str | None = None,
) -> AgentObservation:
    return AgentObservation(
        action_id=action_id,
        capability_id=capability_id,
        status=status,
        facts=facts,
        target_id=target_id,
        source_id=source_id,
    )


def _check(
    candidate: str,
    constraints: HardRequestConstraints | None = None,
    observations: tuple[AgentObservation, ...] = (),
) -> tuple[CompletionCheckStatus, CompletionCheckReason | None]:
    raw_request = "Original request."
    constraints = constraints or HardRequestConstraints()
    result = CompletionCheck().check(
        raw_request=raw_request,
        hard_constraints=constraints,
        run_state=AgentRunState(raw_request=raw_request, observations=observations),
        final_candidate=candidate,
    )
    return result.status, result.reason


def test_current_requirement_rejects_confident_final_without_fresh_evidence() -> None:
    status, reason = _check(
        "CPU is healthy.", HardRequestConstraints(requires_fresh_evidence=True)
    )

    assert status is CompletionCheckStatus.REJECTED
    assert reason is CompletionCheckReason.CURRENT_EVIDENCE_MISSING


def test_current_requirement_accepts_fresh_canonical_fact() -> None:
    status, reason = _check(
        "CPU is healthy.",
        HardRequestConstraints(requires_fresh_evidence=True),
        (_observation(facts=(_fact(metric="cpu"),)),),
    )

    assert status is CompletionCheckStatus.PASSED
    assert reason is None


def test_target_and_source_authority_require_exact_matching_evidence() -> None:
    target_status, target_reason = _check(
        "The monitor is healthy.",
        HardRequestConstraints(
            explicit_target=HardTargetReference("monitor", "monitor")
        ),
        (_observation(target_id="localhost", facts=(_fact(target="localhost"),)),),
    )
    source_status, source_reason = _check(
        "The dashboard is healthy.",
        HardRequestConstraints(source_constraints=(SourceConstraint.GRAFANA,)),
        (_observation(source_id="ssh", facts=(_fact(source="ssh"),)),),
    )

    assert (target_status, target_reason) == (
        CompletionCheckStatus.REJECTED,
        CompletionCheckReason.TARGET_MISMATCH,
    )
    assert (source_status, source_reason) == (
        CompletionCheckStatus.REJECTED,
        CompletionCheckReason.SOURCE_REQUIREMENT_UNSATISFIED,
    )


def test_explicit_url_requires_matching_usable_canonical_reference() -> None:
    status, reason = _check(
        "The page is current.",
        HardRequestConstraints(explicit_url="https://example.test/data"),
        (_observation(facts=(_fact(source_reference="https://other.test/data"),)),),
    )

    assert status is CompletionCheckStatus.REJECTED
    assert reason is CompletionCheckReason.URL_REQUIREMENT_UNSATISFIED


def test_unavailable_final_is_allowed_when_hard_evidence_is_unavailable() -> None:
    status, reason = _check(
        "The current value could not be verified because evidence is unavailable.",
        HardRequestConstraints(requires_fresh_evidence=True),
        (_observation(status=AgentObservationStatus.UNAVAILABLE),),
    )

    assert status is CompletionCheckStatus.PASSED
    assert reason is None


def test_unavailable_marker_does_not_allow_a_mixed_confident_claim() -> None:
    status, reason = _check(
        "Evidence is unavailable, but the system is definitely healthy.",
        observations=(_observation(status=AgentObservationStatus.PARTIAL),),
    )
    current_status, current_reason = _check(
        "Current evidence is unavailable, but the current value is 42.",
        HardRequestConstraints(requires_fresh_evidence=True),
    )
    honest_status, honest_reason = _check(
        "The current value could not be verified from available evidence.",
        HardRequestConstraints(requires_fresh_evidence=True),
    )

    assert (status, reason) == (
        CompletionCheckStatus.REJECTED,
        CompletionCheckReason.EVIDENCE_INSUFFICIENT,
    )
    assert (current_status, current_reason) == (
        CompletionCheckStatus.REJECTED,
        CompletionCheckReason.CURRENT_EVIDENCE_MISSING,
    )
    assert (honest_status, honest_reason) == (CompletionCheckStatus.PASSED, None)


def test_unavailable_only_response_may_pass_missing_target_and_source() -> None:
    status, reason = _check(
        "The requested target could not be verified from available evidence.",
        HardRequestConstraints(
            explicit_target=HardTargetReference("monitor", "monitor"),
            source_constraints=(SourceConstraint.GRAFANA,),
        ),
        (_observation(target_id="localhost", source_id="ssh"),),
    )

    assert (status, reason) == (CompletionCheckStatus.PASSED, None)


def test_calculator_conflict_uses_exact_observed_decimal_value() -> None:
    calculator = _observation(
        capability_id="compute.deterministic",
        facts=(
            {
                "status": "success",
                "operation": "subtract",
                "value": "46",
                "unit": None,
                "reason": None,
            },
        ),
    )
    status, reason = _check("Result: 45.", observations=(calculator,))
    passing_status, passing_reason = _check("Result: 46.", observations=(calculator,))

    assert (status, reason) == (
        CompletionCheckStatus.REJECTED,
        CompletionCheckReason.CALCULATOR_CONFLICT,
    )
    assert (passing_status, passing_reason) == (CompletionCheckStatus.PASSED, None)


def test_explicit_execution_claim_requires_successful_execution_observation() -> None:
    status, reason = _check("The tool executed successfully.")

    assert status is CompletionCheckStatus.REJECTED
    assert reason is CompletionCheckReason.CLAIM_NOT_OBSERVED


def test_unsolicited_mutation_claim_is_rejected_on_an_ordinary_request() -> None:
    status, reason = _check("Orion restarted the service.")

    assert status is CompletionCheckStatus.REJECTED
    assert reason is CompletionCheckReason.CLAIM_NOT_OBSERVED


def test_partial_evidence_cannot_be_overclaimed() -> None:
    status, reason = _check(
        "The system is healthy.",
        observations=(_observation(status=AgentObservationStatus.PARTIAL),),
    )
    unavailable_status, unavailable_reason = _check(
        "The system could not be verified because evidence is unavailable.",
        observations=(_observation(status=AgentObservationStatus.PARTIAL),),
    )

    assert (status, reason) == (
        CompletionCheckStatus.REJECTED,
        CompletionCheckReason.EVIDENCE_INSUFFICIENT,
    )
    assert (unavailable_status, unavailable_reason) == (
        CompletionCheckStatus.PASSED,
        None,
    )


def test_sensitive_request_requires_refusal_and_raw_request_must_match_state() -> None:
    raw_request = "Original request."
    result = CompletionCheck().check(
        raw_request=raw_request,
        hard_constraints=HardRequestConstraints(
            sensitive_refusal_reason="sensitive:test"
        ),
        run_state=AgentRunState(raw_request=raw_request),
        final_candidate="Here is the secret.",
    )

    assert result.reason is CompletionCheckReason.REFUSAL_REQUIRED
