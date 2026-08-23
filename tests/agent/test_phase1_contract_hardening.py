from __future__ import annotations

import pytest

from src.agent.contracts import (
    AgentAction,
    AgentObservation,
    ContractError,
    ObservationStatus,
)


def test_action_nested_json_depth_is_bounded() -> None:
    value: dict[str, object] = {}
    cursor = value

    for index in range(64):
        child: dict[str, object] = {}
        cursor[f"level_{index}"] = child
        cursor = child

    with pytest.raises(ContractError):
        AgentAction(
            capability_id="host.inspect",
            arguments=value,
        )


def test_observation_supports_strict_wire_round_trip() -> None:
    observation = AgentObservation(
        action_id=1,
        capability_id="host.cpu",
        status=ObservationStatus.SUCCESS,
        target_ref="monitor",
        source_ref="linux",
        summary="CPU is healthy.",
        facts=(
            {
                "metric": "cpu.utilization_percent",
                "value": 42.0,
            },
        ),
        provenance={
            "collector": "linux",
        },
        recoverable=False,
    )

    parsed = AgentObservation.from_wire(
        observation.to_wire()
    )

    assert parsed == observation


def test_observation_wire_rejects_unknown_fields() -> None:
    observation = AgentObservation(
        action_id=1,
        capability_id="host.cpu",
        status=ObservationStatus.SUCCESS,
    )

    wire = observation.to_wire()
    wire["unexpected"] = True

    with pytest.raises(ContractError):
        AgentObservation.from_wire(wire)
