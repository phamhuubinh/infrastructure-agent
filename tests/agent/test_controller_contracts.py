from __future__ import annotations

import json
from dataclasses import fields
from types import MappingProxyType

import pytest

from src.agent.controller_contracts import (
    AgentAction,
    AgentDecision,
    AgentDecisionKind,
    AgentObservation,
    AgentObservationStatus,
    AgentRunState,
    ControllerContractError,
    agent_decision_from_json,
    agent_decision_to_json,
    agent_observation_from_json,
    agent_observation_to_json,
    agent_run_state_from_json,
    agent_run_state_to_json,
)


@pytest.mark.parametrize(
    "decision",
    (
        AgentDecision(
            kind=AgentDecisionKind.FINAL,
            goal="Explain the result.",
            final_answer="The service is healthy.",
            clarification_question=None,
        ),
        AgentDecision(
            kind=AgentDecisionKind.DISCOVER,
            goal="Find a matching capability.",
            category="linux",
            clarification_question=None,
        ),
        AgentDecision(
            kind=AgentDecisionKind.ACTION,
            goal="Inspect the service state.",
            action=AgentAction("linux.live", {"service_name": "nginx"}),
            clarification_question=None,
        ),
        AgentDecision(
            kind=AgentDecisionKind.CLARIFY,
            goal="Clarify the requested target.",
            clarification_question="Which registered target should I inspect?",
        ),
        AgentDecision(
            kind=AgentDecisionKind.REFUSE,
            goal="Refuse an unsafe request.",
            clarification_question=None,
            refusal_reason="This request is not supported.",
        ),
    ),
)
def test_every_decision_kind_round_trips(decision: AgentDecision) -> None:
    encoded = agent_decision_to_json(decision)

    assert agent_decision_from_json(encoded) == decision
    assert json.loads(encoded)["k"] == decision.kind.value


@pytest.mark.parametrize(
    "decision",
    (
        AgentDecision(
            kind=AgentDecisionKind.FINAL,
            goal="Answer the request.",
            final_answer="Answer.",
            clarification_question=None,
        ),
        AgentDecision(
            kind=AgentDecisionKind.DISCOVER,
            goal="Discover a capability.",
            category="linux",
            clarification_question=None,
        ),
        AgentDecision(
            kind=AgentDecisionKind.ACTION,
            goal="Inspect a service.",
            action=AgentAction("linux.live"),
            clarification_question=None,
        ),
    ),
)
def test_decision_wire_rejects_mixed_shapes(decision: AgentDecision) -> None:
    payload = decision.to_wire()
    payload["q"] = "Unexpected question."

    with pytest.raises(ValueError, match="exactly"):
        AgentDecision.from_wire(payload)


def test_action_arguments_are_deeply_immutable_and_json_safe() -> None:
    action = AgentAction(
        "linux.live",
        {"filters": {"names": ["nginx", "sshd"]}, "limit": 2},
    )

    assert isinstance(action.arguments, MappingProxyType)
    assert isinstance(action.arguments["filters"], MappingProxyType)
    assert action.to_wire() == {
        "i": "linux.live",
        "a": {"filters": {"names": ["nginx", "sshd"]}, "limit": 2},
    }
    with pytest.raises(TypeError):
        action.arguments["limit"] = 3  # type: ignore[index]
    with pytest.raises(TypeError):
        action.arguments["filters"]["names"] = ()  # type: ignore[index]
    with pytest.raises(TypeError, match="JSON-safe"):
        AgentAction("linux.live", {"invalid": object()})


@pytest.mark.parametrize(
    "arguments",
    (
        {"command": "id"},
        {"credentials": "secret"},
        {"nested": {"api-key": "secret"}},
        {"provider_endpoint": "https://provider.example"},
        {"script": "print('unsafe')"},
    ),
)
def test_action_contract_rejects_command_and_credential_shapes(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="must not contain"):
        AgentAction("linux.live", arguments)

    public_names = {item.name for item in fields(AgentAction)}
    assert public_names == {"capability_id", "arguments"}


def test_observation_serialization_is_bounded_and_omits_raw_payloads() -> None:
    observation = AgentObservation(
        action_id=1,
        capability_id="linux.live",
        status=AgentObservationStatus.PARTIAL,
        facts=({"metric": "service.status", "value": "active"},),
        summary="The service is active.",
        target_id="monitor",
        source_id="linux",
        provenance_references=("fact.service.nginx",),
        reason_code="partial_evidence",
        recoverable=True,
    )

    serialized = observation.to_trace_dict()

    assert agent_observation_from_json(agent_observation_to_json(observation)) == observation
    assert "raw_payload" not in serialized
    assert serialized["f"] == [{"metric": "service.status", "value": "active"}]
    with pytest.raises(ValueError, match="at most"):
        AgentObservation(
            action_id=1,
            capability_id="linux.live",
            status=AgentObservationStatus.SUCCESS,
            facts=tuple({"metric": str(index)} for index in range(13)),
        )


def test_run_state_is_inert_and_trace_projection_excludes_raw_request() -> None:
    state = AgentRunState(
        raw_request="Check the CPU on monitor.",
        hard_constraint_reference="read_only",
        hard_constraint_snapshot={"read_only": True},
    )

    assert state.disclosed_capability_categories == ()
    assert state.disclosed_capability_detail_ids == ()
    assert state.observations == ()
    assert state.action_count == 0
    assert state.terminal is False
    assert "localhost" not in str(state.to_wire()).casefold()
    assert "q" not in state.to_trace_dict()
    assert agent_run_state_from_json(agent_run_state_to_json(state)) == state


def test_wire_rejects_unknown_enums_duplicate_keys_and_invalid_terminal_shape() -> None:
    payload = AgentDecision().to_wire()
    payload["k"] = "execute"
    with pytest.raises(ControllerContractError, match="unknown enum"):
        AgentDecision.from_wire(payload)

    encoded = agent_decision_to_json(AgentDecision())
    duplicate = encoded.replace('"v":1', '"v":1,"v":1', 1)
    with pytest.raises(ControllerContractError, match="Duplicate JSON field"):
        agent_decision_from_json(duplicate)

    with pytest.raises(ValueError, match="set together"):
        AgentRunState(raw_request="Check CPU.", terminal=True)
