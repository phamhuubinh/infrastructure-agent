from __future__ import annotations

import json
from dataclasses import fields
from types import MappingProxyType

import pytest

from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    AgentObservation,
    ContractError,
    DecisionKind,
    ObservationStatus,
    decision_from_json,
    decision_to_json,
)
from src.agent.permissions import EffectClass, PermissionMode


def test_action_is_readable_and_carries_semantic_refs() -> None:
    action = AgentAction(
        capability_id="host.cpu",
        target_ref="monitor",
        source_ref="linux",
        arguments={"window_seconds": 60},
        activity_text="Checking CPU on monitor",
    )

    assert action.to_wire() == {
        "capability_id": "host.cpu",
        "target_ref": "monitor",
        "source_ref": "linux",
        "arguments": {"window_seconds": 60},
        "activity_text": "Checking CPU on monitor",
    }
    assert isinstance(action.arguments, MappingProxyType)
    assert {item.name for item in fields(AgentAction)} == {
        "capability_id",
        "target_ref",
        "source_ref",
        "arguments",
        "activity_text",
    }


@pytest.mark.parametrize(
    "decision",
    (
        AgentDecision(
            kind=DecisionKind.FINAL,
            goal="Answer the user.",
            answer="Done.",
        ),
        AgentDecision(
            kind=DecisionKind.DISCOVER,
            goal="Find a host capability.",
            category="host",
        ),
        AgentDecision(
            kind=DecisionKind.ACTION,
            goal="Inspect CPU.",
            action=AgentAction(
                capability_id="host.cpu",
                target_ref="monitor",
                activity_text="Checking CPU",
            ),
        ),
        AgentDecision(
            kind=DecisionKind.CLARIFY,
            goal="Resolve missing information.",
            question="Which target should I inspect?",
        ),
        AgentDecision(
            kind=DecisionKind.REFUSE,
            goal="Reject unsupported execution.",
            reason="The requested action is unavailable.",
        ),
    ),
)
def test_decisions_round_trip_with_readable_wire(decision: AgentDecision) -> None:
    encoded = decision_to_json(decision)
    payload = json.loads(encoded)

    assert payload["version"] == 2
    assert payload["kind"] == decision.kind.value
    assert "goal" in payload
    assert "v" not in payload
    assert "k" not in payload
    assert decision_from_json(encoded) == decision


def test_decision_rejects_mixed_body() -> None:
    with pytest.raises(ValueError, match="exactly answer"):
        AgentDecision(
            kind=DecisionKind.FINAL,
            goal="Answer.",
            answer="Result.",
            question="Unexpected.",
        )


@pytest.mark.parametrize(
    "arguments",
    (
        {"command": "id"},
        {"password": "secret"},
        {"api-key": "secret"},
        {"nested": {"token": "secret"}},
    ),
)
def test_action_rejects_execution_and_secret_authority(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ContractError, match="must not contain"):
        AgentAction("host.cpu", arguments=arguments)


def test_observation_is_compact_and_readable() -> None:
    observation = AgentObservation(
        action_id=1,
        capability_id="host.cpu",
        status=ObservationStatus.SUCCESS,
        target_ref="monitor",
        source_ref="linux",
        summary="CPU collected.",
        facts=({"metric": "cpu.utilization_percent", "value": 42.0},),
    )

    assert observation.to_wire()["target_ref"] == "monitor"
    assert observation.to_wire()["facts"] == [
        {"metric": "cpu.utilization_percent", "value": 42.0}
    ]


def test_permission_matrix() -> None:
    assert PermissionMode.READ.allows(EffectClass.READ)
    assert not PermissionMode.READ.allows(EffectClass.WRITE)

    assert PermissionMode.RW_ASK.allows(EffectClass.READ)
    assert PermissionMode.RW_ASK.allows(EffectClass.WRITE)
    assert PermissionMode.RW_ASK.requires_approval(EffectClass.WRITE)
    assert not PermissionMode.RW_ASK.requires_approval(EffectClass.READ)

    assert PermissionMode.RW_FULL.allows(EffectClass.READ)
    assert PermissionMode.RW_FULL.allows(EffectClass.WRITE)
    assert not PermissionMode.RW_FULL.requires_approval(EffectClass.WRITE)
