from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.agent.controller_contracts import (
    AgentObservation,
    AgentObservationStatus,
    agent_observation_to_json,
)
from src.pipeline.agent_action_executor import (
    AgentActionExecutionReason,
    AgentActionExecutionResult,
    AgentActionExecutionStatus,
)
from src.pipeline.agent_action_validator import (
    AgentActionToolBudget,
    AgentActionValidationReason,
    AgentActionValidationResult,
    AgentActionValidationStatus,
)
from src.pipeline.agent_observation_serializer import (
    MAX_AGENT_OBSERVATION_BYTES,
    MAX_FACTS_PER_AGENT_OBSERVATION,
    MAX_RETAINED_AGENT_OBSERVATIONS,
    retain_agent_observations,
    serialize_calculator_observation,
    serialize_control_feedback,
    serialize_discovery_observation,
    serialize_execution_observation,
    serialize_validation_failure,
)
from src.pipeline.basic_calculator import (
    CalculatorContractResult,
    CalculatorOperation,
    CalculatorResultStatus,
)
from src.pipeline.controller_capability_discovery import (
    CapabilityDiscoveryResult,
    CapabilityDiscoveryStatus,
)
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance
from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.capability_result import CapabilityStatus
from src.tool.errors import (
    CapabilityError,
    CapabilityErrorCategory,
    CapabilityErrorCode,
)

NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def _fact(
    index: int,
    *,
    validity: FactValidity = FactValidity.VALID,
    freshness: FactFreshness = FactFreshness.FRESH,
    value: object | None = None,
) -> Fact:
    provenance = Provenance(
        source="linux",
        capability="get_cpu",
        target="server-1",
        observed_at=NOW,
        source_reference="https://metrics.example/cpu?token=fixture-secret",
        command_ids=("cmd-fixture",),
        parameters=(("password", "fixture-secret"),),
    )
    return Fact(
        subject="system",
        metric=f"system.metric_{index}",
        value=(index if value is None and validity is FactValidity.VALID else value),
        unit="count" if validity is FactValidity.VALID else "",
        observed_at=NOW,
        collected_at=NOW,
        source="linux",
        target="server-1",
        validity=validity,
        freshness=freshness,
        confidence=1.0,
        provenance=provenance,
    )


def _validation(
    status: AgentActionValidationStatus = AgentActionValidationStatus.VALID,
    reason: AgentActionValidationReason = AgentActionValidationReason.VALIDATED,
) -> AgentActionValidationResult:
    return AgentActionValidationResult(
        status,
        reason,
        "host.get_cpu",
        target_id="server-1",
        source_family="linux",
        source_id="server-1",
        normalized_arguments={"ignored": "must-not-appear"},
    )


def _execution(evidence: EvidencePackage) -> AgentActionExecutionResult:
    return AgentActionExecutionResult(
        validation=_validation(),
        status=AgentActionExecutionStatus.PARTIAL,
        reason=AgentActionExecutionReason.DISPATCHED,
        budget=AgentActionToolBudget(actions_used=1, tools_used=1),
        source_id="server-1",
        evidence=evidence,
        dispatched=True,
    )


def test_large_evidence_is_bounded_and_excludes_raw_execution_payloads() -> None:
    error = CapabilityError(
        CapabilityErrorCode.COLLECTION_FAILED,
        CapabilityErrorCategory.COMMAND,
        "collection token=fixture-secret",
        True,
    )
    evidence = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.PARTIAL,
        facts=tuple(_fact(index, value="x" * 400) for index in range(10)),
        warnings=("one sample unavailable",) * 4,
        raw_data={"command": "cat /etc/shadow", "token": "fixture-secret"},
        data={"stdout": "fixture raw API response"},
        command_results=(
            CommandResult(
                CommandStatus.NON_ZERO_EXIT,
                stdout="fixture stdout",
                stderr="fixture stderr",
            ),
        ),
        capability_error=error,
    )

    observation = serialize_execution_observation(3, _execution(evidence))
    serialized = agent_observation_to_json(observation)

    assert len(serialized.encode()) <= MAX_AGENT_OBSERVATION_BYTES
    assert observation.status is AgentObservationStatus.PARTIAL
    assert "partial evidence" in (observation.summary or "")
    assert len(observation.facts) <= MAX_FACTS_PER_AGENT_OBSERVATION
    assert all(
        fact["value"] == {"value_omitted": "oversize"} for fact in observation.facts
    )
    for forbidden in (
        "fixture-secret",
        "cat /etc/shadow",
        "fixture stdout",
        "fixture stderr",
        "fixture raw API response",
        "command_ids",
        "parameters",
        "raw_data",
    ):
        assert forbidden not in serialized


def test_evidence_preserves_identity_and_compact_canonical_provenance() -> None:
    fact = _fact(1)
    evidence = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.VALID,
        facts=(fact,),
    )

    observation = serialize_execution_observation(4, _execution(evidence))
    compact = observation.facts[0]

    assert observation.status is AgentObservationStatus.SUCCESS
    assert observation.capability_id == "host.get_cpu"
    assert observation.target_id == observation.source_id == "server-1"
    assert compact["provenance_id"] == fact.provenance.id
    assert compact["source_reference"] == (
        "https://metrics.example/cpu?token=%3Credacted%3E"
    )
    assert observation.provenance_references == (fact.provenance.id,)
    assert "command_ids" not in compact
    assert "parameters" not in compact


def test_compact_external_fact_retains_safe_provider_only() -> None:
    original = _fact(1)
    fact = Fact(
        subject=original.subject,
        metric=original.metric,
        value=original.value,
        unit=original.unit,
        observed_at=original.observed_at,
        collected_at=original.collected_at,
        source="internet",
        target="example.com",
        validity=original.validity,
        freshness=original.freshness,
        confidence=original.confidence,
        provenance=Provenance(
            source="internet",
            capability="web_fetch",
            target="example.com",
            observed_at=NOW,
            source_reference="https://example.com/release",
        ),
        dimensions={"provider": "fixture-search", "endpoint": "https://secret.example"},
    )
    observation = serialize_execution_observation(
        12,
        _execution(EvidencePackage("internet.current", "current", facts=(fact,))),
    )

    compact = observation.facts[0]
    assert compact["provider"] == "fixture-search"
    assert "endpoint" not in compact


def test_priority_preserves_contradiction_before_ordinary_facts() -> None:
    facts = (_fact(99, validity=FactValidity.CONTRADICTORY, value=None),) + tuple(
        _fact(index) for index in range(10)
    )
    evidence = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.PARTIAL,
        facts=facts,
    )

    observation = serialize_execution_observation(5, _execution(evidence))

    assert observation.status is AgentObservationStatus.PARTIAL
    assert observation.facts[0]["validity"] == FactValidity.CONTRADICTORY.value


def test_valid_empty_evidence_remains_distinct_from_partial() -> None:
    empty = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.VALID_EMPTY,
    )
    empty_fact = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.VALID_EMPTY,
        facts=(_fact(1, validity=FactValidity.VALID_EMPTY, value=None),),
    )

    assert (
        serialize_execution_observation(6, _execution(empty)).status
        is AgentObservationStatus.EMPTY_SUCCESS
    )
    assert (
        serialize_execution_observation(7, _execution(empty_fact)).status
        is AgentObservationStatus.EMPTY_SUCCESS
    )


def test_nominal_success_with_unusable_fact_becomes_partial() -> None:
    packages = (
        EvidencePackage(
            capability_name="host.get_cpu",
            evidence_name="cpu",
            status=CapabilityStatus.VALID,
            facts=(_fact(1, validity=FactValidity.CONTRADICTORY, value=None),),
        ),
        EvidencePackage(
            capability_name="host.get_cpu",
            evidence_name="cpu",
            status=CapabilityStatus.VALID_EMPTY,
            facts=(
                _fact(
                    2,
                    freshness=FactFreshness.STALE,
                    value=2,
                ),
            ),
        ),
        EvidencePackage(
            capability_name="host.get_cpu",
            evidence_name="cpu",
            status=CapabilityStatus.VALID,
            facts=(
                _fact(
                    3,
                    validity=FactValidity.COMMAND_FAILED,
                    value=None,
                ),
            ),
        ),
    )

    observations = tuple(
        serialize_execution_observation(index, _execution(package))
        for index, package in enumerate(packages, start=8)
    )

    assert all(
        observation.status is AgentObservationStatus.PARTIAL
        for observation in observations
    )
    assert observations[0].reason_code == "partial_evidence"
    assert observations[0].reason_code != CapabilityStatus.VALID.value
    assert observations[1].reason_code == "partial_evidence"
    assert observations[1].reason_code != CapabilityStatus.VALID_EMPTY.value
    assert observations[2].reason_code == "partial_evidence"


def test_native_partial_preserves_structured_capability_error() -> None:
    error = CapabilityError(
        CapabilityErrorCode.TIMEOUT,
        CapabilityErrorCategory.TRANSPORT,
        "collection timed out",
        True,
    )
    evidence = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.PARTIAL,
        capability_error=error,
    )

    observation = serialize_execution_observation(11, _execution(evidence))

    assert observation.status is AgentObservationStatus.PARTIAL
    assert observation.reason_code == CapabilityErrorCode.TIMEOUT.value
    assert observation.recoverable is True


def test_unsafe_canonical_fact_value_is_omitted_as_a_whole() -> None:
    unsafe_value = {
        "safe": "active",
        "nested": {
            "command": "curl -H 'Authorization: Bearer fixture-secret'",
            "stdout": "fixture stdout",
            "stderr": "fixture stderr",
            "token": "fixture-secret",
            "password": "fixture-secret",
            "credentials": "fixture-secret",
        },
    }
    safe_value = {"state": "active", "counts": [1, 2]}
    evidence = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.VALID,
        facts=(_fact(1, value=unsafe_value), _fact(2, value=safe_value)),
    )

    observation = serialize_execution_observation(11, _execution(evidence))
    serialized = agent_observation_to_json(observation)
    unsafe_fact, safe_fact = observation.facts

    assert unsafe_fact["value"] == {"value_omitted": "unsafe"}
    assert unsafe_fact["id"] == evidence.facts[0].id
    assert unsafe_fact["metric"] == evidence.facts[0].metric
    assert unsafe_fact["validity"] == FactValidity.VALID.value
    assert unsafe_fact["provenance_id"] == evidence.facts[0].provenance.id
    assert safe_fact["value"] == {"state": "active", "counts": (1, 2)}
    for forbidden in (
        "fixture-secret",
        "curl -H",
        "fixture stdout",
        "fixture stderr",
        "Authorization",
    ):
        assert forbidden not in serialized


def test_validation_calculator_discovery_and_control_feedback_are_typed() -> None:
    invalid = serialize_validation_failure(
        6,
        _validation(
            AgentActionValidationStatus.REJECT,
            AgentActionValidationReason.ARGUMENT_INVALID,
        ),
    )
    forbidden = serialize_validation_failure(
        7,
        _validation(
            AgentActionValidationStatus.REJECT,
            AgentActionValidationReason.SOURCE_FORBIDDEN,
        ),
    )
    budget = serialize_validation_failure(
        8,
        _validation(
            AgentActionValidationStatus.UNAVAILABLE,
            AgentActionValidationReason.BUDGET_EXHAUSTED,
        ),
    )
    calculator = serialize_calculator_observation(
        9,
        CalculatorContractResult(
            CalculatorResultStatus.SUCCESS,
            CalculatorOperation.SUBTRACT,
            Decimal("46"),
        ),
    )
    discovery = serialize_discovery_observation(
        10,
        CapabilityDiscoveryResult(
            CapabilityDiscoveryStatus.DISCOVERED,
            "calculator",
            ({"capability_id": "compute.deterministic"},),
        ),
    )
    control = serialize_control_feedback(
        11,
        status=AgentObservationStatus.UNAVAILABLE,
        reason_code="source_unavailable",
        safe_detail="grafana token=fixture-secret",
        source_id="grafana",
        recoverable=True,
    )

    assert (invalid.status, invalid.reason_code, invalid.recoverable) == (
        AgentObservationStatus.INVALID_ACTION,
        "argument_invalid",
        True,
    )
    assert (forbidden.status, forbidden.recoverable) == (
        AgentObservationStatus.BLOCKED,
        False,
    )
    assert (budget.status, budget.recoverable) == (
        AgentObservationStatus.UNAVAILABLE,
        False,
    )
    assert calculator.facts == (
        {
            "status": "success",
            "operation": "subtract",
            "value": "46",
            "unit": None,
            "reason": None,
        },
    )
    assert calculator.provenance_references == ()
    assert discovery.capability_id == "discovery.calculator"
    assert "compute.deterministic" not in (discovery.summary or "")
    assert "fixture-secret" not in agent_observation_to_json(control)


def test_retention_keeps_newest_failure_and_exact_identity_deterministically() -> None:
    observations = tuple(
        AgentObservation(
            action_id=index,
            capability_id="host.get_cpu" if index in {1, 7} else "host.get_memory",
            status=(
                AgentObservationStatus.FAILED
                if index == 2
                else AgentObservationStatus.SUCCESS
            ),
            target_id="server-1" if index in {1, 7} else "server-2",
        )
        for index in range(1, 9)
    )

    retained = retain_agent_observations(
        observations,
        capability_id="host.get_cpu",
        target_id="server-1",
    )

    assert len(retained) == MAX_RETAINED_AGENT_OBSERVATIONS
    assert retained[-1].action_id == 8
    assert any(item.action_id == 2 for item in retained)
    assert {1, 7}.issubset({item.action_id for item in retained})
    assert tuple(item.action_id for item in retained) == tuple(
        sorted(item.action_id for item in retained)
    )


def test_serializer_output_is_deterministic() -> None:
    fact = _fact(1)
    evidence = EvidencePackage(
        capability_name="host.get_cpu",
        evidence_name="cpu",
        status=CapabilityStatus.VALID,
        facts=(fact,),
    )

    first = serialize_execution_observation(12, _execution(evidence))
    second = serialize_execution_observation(12, _execution(evidence))

    assert agent_observation_to_json(first) == agent_observation_to_json(second)
