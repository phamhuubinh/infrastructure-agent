"""Provider-neutral transport for Orion agent decisions.

This module defines only the structured model-output boundary. It grants no
capability, target, source, or execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.agent.contracts import (
    MAX_CAPABILITY_ID_CHARS,
    MAX_REFERENCE_CHARS,
    MAX_TEXT_CHARS,
    PROTOCOL_VERSION,
    AgentDecision,
    ContractError,
    decision_from_json,
)


def agent_decision_json_schema(
    selected_capability_schema: Mapping[str, object] | None = None,
    *,
    allowed_kinds: tuple[str, ...] | None = None,
    allowed_discovery_groups: tuple[str, ...] | None = None,
    allowed_action_capability_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Return the canonical structured-output schema for one agent decision."""

    text = {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS}
    reference = {"type": "string", "minLength": 1, "maxLength": MAX_REFERENCE_CHARS}

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

    target_ref_schema: dict[str, object] | None = None
    source_ref_schema: dict[str, object] | None = None
    if selected_capability_schema is not None:
        (
            capability_id,
            arguments_schema,
            target_ref_schema,
            source_ref_schema,
        ) = _selected_action_transport(
            selected_capability_schema
        )
        capability_id_schema = {
            "type": "string",
            "enum": [capability_id],
        }
    if allowed_action_capability_ids is not None:
        if (
            not allowed_action_capability_ids
            or len(allowed_action_capability_ids)
            != len(set(allowed_action_capability_ids))
            or any(
                not isinstance(capability_id, str)
                or not capability_id
                or len(capability_id) > MAX_CAPABILITY_ID_CHARS
                for capability_id in allowed_action_capability_ids
            )
        ):
            raise ValueError(
                "allowed_action_capability_ids must contain unique bounded IDs."
            )
        if selected_capability_schema is not None:
            raise ValueError(
                "allowed_action_capability_ids cannot accompany selected schema."
            )
        capability_id_schema = {
            "type": "string",
            "enum": list(allowed_action_capability_ids),
        }

    action_properties: dict[str, object] = {
        "capability_id": capability_id_schema,
        "arguments": arguments_schema,
        "activity_text": text,
    }
    action_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "capability_id",
            "arguments",
        ],
        "properties": action_properties,
    }
    if selected_capability_schema is None:
        action_properties["target_ref"] = reference
        action_properties["source_ref"] = reference
    elif target_ref_schema is not None:
        action_properties["target_ref"] = target_ref_schema
    if selected_capability_schema is not None and source_ref_schema is not None:
        action_properties["source_ref"] = source_ref_schema

    decision_bodies = (
        ("final", "answer"),
        ("discover", "category"),
        ("action", "action"),
        ("clarify", "question"),
        ("refuse", "reason"),
    )

    valid_kinds = tuple(kind for kind, _ in decision_bodies)
    selected_kinds = allowed_kinds or valid_kinds

    if (
        not selected_kinds
        or len(selected_kinds) != len(set(selected_kinds))
        or any(kind not in valid_kinds for kind in selected_kinds)
    ):
        raise ValueError("allowed_kinds contains invalid decision kinds.")
    if allowed_discovery_groups is not None:
        if (
            not allowed_discovery_groups
            or len(allowed_discovery_groups) != len(set(allowed_discovery_groups))
            or any(
                not isinstance(group, str) or not group
                for group in allowed_discovery_groups
            )
        ):
            raise ValueError(
                "allowed_discovery_groups must contain unique non-empty strings."
            )
        if "discover" not in selected_kinds:
            raise ValueError(
                "allowed_discovery_groups requires discover to be allowed."
            )
    if allowed_action_capability_ids is not None and "action" not in selected_kinds:
        raise ValueError("allowed_action_capability_ids requires action to be allowed.")

    branches: list[dict[str, object]] = []
    for kind, body_field in decision_bodies:
        if kind not in selected_kinds:
            continue
        properties: dict[str, object] = {
            "version": {
                "type": "integer",
                "enum": [PROTOCOL_VERSION],
            },
            "kind": {
                "type": "string",
                "enum": [kind],
            },
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
        if kind == "discover" and allowed_discovery_groups is not None:
            properties["category"] = {
                "type": "string",
                "enum": list(allowed_discovery_groups),
            }
        if kind == "final":
            properties["claims"] = _final_claims_schema(
                capability_id_schema,
                reference,
            )

        required = ["version", "kind", body_field]
        branches.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": properties,
            }
        )

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OrionAgentDecisionV3",
        "oneOf": branches,
    }


def parse_agent_decision_payload(payload: object) -> AgentDecision:
    """Strictly normalize provider output into the canonical decision contract."""

    if isinstance(payload, dict):
        return AgentDecision.from_wire(payload)

    if isinstance(payload, (str, bytes)):
        return decision_from_json(payload)

    raise ContractError("Provider payload must be a decision object or JSON text.")


def _final_claims_schema(
    capability_id_schema: Mapping[str, object],
    nullable_reference: Mapping[str, object],
) -> dict[str, object]:
    """Return the FINAL-only claims constraint used by its exact branch."""
    return {
        "type": "array",
        "maxItems": 16,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "action_id",
                "capability_id",
            ],
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["observation", "deterministic_result"],
                },
                "action_id": {"type": "integer", "minimum": 1},
                "capability_id": dict(capability_id_schema),
                "target_ref": dict(nullable_reference),
                "source_ref": dict(nullable_reference),
                "require_fresh": {"type": "boolean"},
                "result": {
                    "type": "object", "minProperties": 1
                },
            },
        },
    }


def _selected_action_transport(
    value: Mapping[str, object],
) -> tuple[str, dict[str, object], dict[str, object] | None, dict[str, object] | None]:
    if not isinstance(value, Mapping):
        raise TypeError("selected_capability_schema must be a mapping.")

    capability_id = value.get("capability_id")
    if not isinstance(capability_id, str) or not capability_id:
        raise ValueError("selected capability schema requires capability_id.")

    arguments_schema = value.get("arguments_schema")
    if not isinstance(arguments_schema, Mapping):
        raise ValueError("selected capability schema requires arguments_schema.")

    branches = arguments_schema.get("oneOf")
    if branches is not None:
        if not isinstance(branches, list) or not branches:
            raise ValueError("arguments_schema.oneOf must be a non-empty array.")
        for branch in branches:
            _closed_object_schema(branch)
    else:
        _closed_object_schema(arguments_schema)

    return (
        capability_id,
        dict(arguments_schema),
        _selected_reference_schema(value, "target_ref"),
        _selected_reference_schema(value, "source_ref"),
    )


def _closed_object_schema(value: object) -> None:
    if not isinstance(value, Mapping) or value.get("type") != "object":
        raise ValueError("arguments_schema must describe a closed object.")
    if value.get("additionalProperties") is not False:
        raise ValueError("arguments_schema must set additionalProperties to false.")
    properties = value.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError("arguments_schema.properties must be an object.")
    required = value.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise ValueError("arguments_schema.required must be an array of strings.")
    undeclared = set(required) - set(properties)
    if undeclared:
        raise ValueError("arguments_schema.required references undeclared properties.")


def _selected_reference_schema(
    selected: Mapping[str, object],
    field_name: str,
) -> dict[str, object] | None:
    value = selected.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"selected capability schema requires {field_name} authority.")
    applicable = value.get("applicable")
    if not isinstance(applicable, bool):
        raise ValueError(f"{field_name}.applicable must be boolean.")
    allowed_refs = value.get("allowed_refs")
    if not applicable:
        if allowed_refs is not None:
            raise ValueError(f"non-applicable {field_name} cannot disclose refs.")
        return None
    if not isinstance(allowed_refs, list) or any(
        not isinstance(ref, str) or not ref or len(ref) > MAX_REFERENCE_CHARS
        for ref in allowed_refs
    ) or len(allowed_refs) != len(set(allowed_refs)):
        raise ValueError(f"{field_name}.allowed_refs must be unique bounded refs.")
    if not allowed_refs:
        return None
    return {"type": "string", "enum": list(allowed_refs)}
