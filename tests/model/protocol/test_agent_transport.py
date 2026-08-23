from __future__ import annotations

import json

import pytest

from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    ContractError,
    DecisionKind,
    decision_to_json,
)
from src.model.protocol.agent_transport import (
    agent_decision_json_schema,
    parse_agent_decision_payload,
)


def _selected_schema() -> dict[str, object]:
    return {
        "capability_id": "host.cpu",
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["window_seconds"],
            "properties": {
                "window_seconds": {
                    "type": "integer",
                    "minimum": 1,
                }
            },
        },
    }


def test_schema_uses_readable_protocol_fields() -> None:
    schema = agent_decision_json_schema()

    assert schema["title"] == "OrionAgentDecisionV2"
    assert schema["required"] == [
        "version",
        "kind",
        "goal",
        "category",
        "action",
        "answer",
        "question",
        "reason",
    ]

    properties = schema["properties"]

    assert properties["version"]["enum"] == [2]
    assert properties["kind"]["enum"] == [
        "final",
        "discover",
        "action",
        "clarify",
        "refuse",
    ]

    for legacy in ("v", "k", "g", "c", "a", "f", "q", "r"):
        assert legacy not in properties


def test_action_schema_exposes_semantic_refs_and_activity() -> None:
    schema = agent_decision_json_schema(_selected_schema())

    action_branch = next(
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )
    action = action_branch["properties"]["action"]

    assert action["required"] == [
        "capability_id",
        "target_ref",
        "source_ref",
        "arguments",
        "activity_text",
    ]
    assert action["properties"]["capability_id"] == {
        "type": "string",
        "enum": ["host.cpu"],
    }
    assert action["properties"]["arguments"] == {
        "type": "object",
        "additionalProperties": False,
        "required": ["window_seconds"],
        "properties": {
            "window_seconds": {
                "type": "integer",
                "minimum": 1,
            }
        },
    }
    assert "target_ref" in action["properties"]
    assert "source_ref" in action["properties"]
    assert "activity_text" in action["properties"]


def test_dict_provider_payload_parses_to_canonical_decision() -> None:
    payload = {
        "version": 2,
        "kind": "action",
        "goal": "Inspect CPU.",
        "category": None,
        "action": {
            "capability_id": "host.cpu",
            "target_ref": "monitor",
            "source_ref": "linux",
            "arguments": {"window_seconds": 60},
            "activity_text": "Checking CPU",
        },
        "answer": None,
        "question": None,
        "reason": None,
    }

    decision = parse_agent_decision_payload(payload)

    assert decision == AgentDecision(
        kind=DecisionKind.ACTION,
        goal="Inspect CPU.",
        action=AgentAction(
            capability_id="host.cpu",
            target_ref="monitor",
            source_ref="linux",
            arguments={"window_seconds": 60},
            activity_text="Checking CPU",
        ),
    )


def test_json_provider_payload_parses_to_canonical_decision() -> None:
    decision = AgentDecision(
        kind=DecisionKind.FINAL,
        goal="Answer the user.",
        answer="CPU is healthy.",
    )

    parsed = parse_agent_decision_payload(decision_to_json(decision))

    assert parsed == decision


def test_old_compact_wire_format_is_rejected() -> None:
    legacy = json.dumps(
        {
            "v": 1,
            "k": "final",
            "g": "Answer.",
            "c": None,
            "a": None,
            "f": "Done.",
            "q": None,
            "r": None,
        }
    )

    with pytest.raises(ContractError):
        parse_agent_decision_payload(legacy)


@pytest.mark.parametrize(
    "schema",
    (
        {
            "capability_id": "host.cpu",
            "arguments_schema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "capability_id": "host.cpu",
            "arguments_schema": {
                "type": "array",
                "additionalProperties": False,
                "properties": {},
            },
        },
        {
            "capability_id": "host.cpu",
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["missing"],
                "properties": {},
            },
        },
    ),
)
def test_selected_capability_transport_requires_closed_schema(
    schema: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        agent_decision_json_schema(schema)


def test_provider_payload_type_fails_closed() -> None:
    with pytest.raises(
        ContractError,
        match="decision object or JSON text",
    ):
        parse_agent_decision_payload(["not", "a", "decision"])



def test_schema_limits_match_canonical_contract() -> None:
    from src.agent.contracts import (
        MAX_CAPABILITY_ID_CHARS,
        MAX_REFERENCE_CHARS,
    )

    schema = agent_decision_json_schema()
    action = schema["properties"]["action"]["anyOf"][0]
    properties = action["properties"]

    assert (
        properties["capability_id"]["maxLength"]
        == MAX_CAPABILITY_ID_CHARS
    )
    assert (
        properties["target_ref"]["anyOf"][0]["maxLength"]
        == MAX_REFERENCE_CHARS
    )
    assert (
        properties["source_ref"]["anyOf"][0]["maxLength"]
        == MAX_REFERENCE_CHARS
    )
