"""Provider-neutral transport for Orion agent decisions.

This module defines only the structured model-output boundary. It grants no
capability, target, source, or execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.agent.contracts import (
    MAX_CAPABILITY_ID_CHARS,
    MAX_GOAL_CHARS,
    MAX_REFERENCE_CHARS,
    MAX_TEXT_CHARS,
    PROTOCOL_VERSION,
    AgentDecision,
    ContractError,
    decision_from_json,
)


def agent_decision_json_schema(
    selected_capability_schema: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the canonical structured-output schema for one agent decision."""

    nullable_text = _nullable_text(MAX_TEXT_CHARS)
    nullable_reference = {
        "anyOf": [
            {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_REFERENCE_CHARS,
            },
            {"type": "null"},
        ]
    }

    capability_id_schema: dict[str, object] = {
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_CAPABILITY_ID_CHARS,
    }
    arguments_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }

    if selected_capability_schema is not None:
        capability_id, arguments_schema = _selected_action_transport(
            selected_capability_schema
        )
        capability_id_schema = {
            "type": "string",
            "enum": [capability_id],
        }

    action_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "capability_id",
            "target_ref",
            "source_ref",
            "arguments",
            "activity_text",
        ],
        "properties": {
            "capability_id": capability_id_schema,
            "target_ref": nullable_reference,
            "source_ref": nullable_reference,
            "arguments": arguments_schema,
            "activity_text": nullable_text,
        },
    }

    common_properties: dict[str, object] = {
        "version": {
            "type": "integer",
            "enum": [PROTOCOL_VERSION],
        },
        "kind": {
            "type": "string",
            "enum": [
                "final",
                "discover",
                "action",
                "clarify",
                "refuse",
            ],
        },
        "goal": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_GOAL_CHARS,
        },
        "category": nullable_text,
        "action": {
            "anyOf": [
                action_schema,
                {"type": "null"},
            ]
        },
        "answer": nullable_text,
        "question": nullable_text,
        "reason": nullable_text,
    }

    branches: list[dict[str, object]] = []
    for kind, body_field in (
        ("final", "answer"),
        ("discover", "category"),
        ("action", "action"),
        ("clarify", "question"),
        ("refuse", "reason"),
    ):
        properties: dict[str, object] = {
            "version": {
                "type": "integer",
                "enum": [PROTOCOL_VERSION],
            },
            "kind": {
                "type": "string",
                "enum": [kind],
            },
            "goal": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_GOAL_CHARS,
            },
            "category": {"type": "null"},
            "action": {"type": "null"},
            "answer": {"type": "null"},
            "question": {"type": "null"},
            "reason": {"type": "null"},
        }

        properties[body_field] = (
            action_schema
            if body_field == "action"
            else {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_TEXT_CHARS,
            }
        )

        branches.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "version",
                    "kind",
                    "goal",
                    "category",
                    "action",
                    "answer",
                    "question",
                    "reason",
                ],
                "properties": properties,
            }
        )

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OrionAgentDecisionV2",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "version",
            "kind",
            "goal",
            "category",
            "action",
            "answer",
            "question",
            "reason",
        ],
        "properties": common_properties,
        "oneOf": branches,
    }


def parse_agent_decision_payload(payload: object) -> AgentDecision:
    """Strictly normalize provider output into the canonical decision contract."""

    if isinstance(payload, dict):
        return AgentDecision.from_wire(payload)

    if isinstance(payload, (str, bytes)):
        return decision_from_json(payload)

    raise ContractError(
        "Provider payload must be a decision object or JSON text."
    )


def _nullable_text(max_length: int) -> dict[str, object]:
    return {
        "anyOf": [
            {
                "type": "string",
                "minLength": 1,
                "maxLength": max_length,
            },
            {"type": "null"},
        ]
    }


def _selected_action_transport(
    value: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    if not isinstance(value, Mapping):
        raise TypeError("selected_capability_schema must be a mapping.")

    capability_id = value.get("capability_id")
    if not isinstance(capability_id, str) or not capability_id:
        raise ValueError(
            "selected capability schema requires capability_id."
        )

    arguments_schema = value.get("arguments_schema")
    if not isinstance(arguments_schema, Mapping):
        raise ValueError(
            "selected capability schema requires arguments_schema."
        )

    if arguments_schema.get("type") != "object":
        raise ValueError("arguments_schema must describe an object.")

    if arguments_schema.get("additionalProperties") is not False:
        raise ValueError(
            "arguments_schema must set additionalProperties to false."
        )

    properties = arguments_schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError(
            "arguments_schema.properties must be an object."
        )

    required = arguments_schema.get("required", [])
    if not isinstance(required, list) or any(
        not isinstance(item, str) for item in required
    ):
        raise ValueError(
            "arguments_schema.required must be an array of strings."
        )

    undeclared = set(required) - set(properties)
    if undeclared:
        raise ValueError(
            "arguments_schema.required references undeclared properties."
        )

    return capability_id, dict(arguments_schema)
