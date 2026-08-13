"""Strict, bounded wire contract for :mod:`semantic_plan`.

The compact versioned mapping is the only model/harness exchange shape.  It
uses short stable keys to keep planner input/output small, rejects missing or
unknown fields, and never coerces malformed data into executable defaults.
"""

from __future__ import annotations

import json
from enum import Enum
from json import JSONDecodeError
from typing import TypeVar

from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
    TargetReference,
    TargetReferenceKind,
)

SEMANTIC_PLAN_WIRE_VERSION = 1
MAX_SEMANTIC_PLAN_BYTES = 4096
MAX_SEMANTIC_TEXT_LENGTH = 256
MAX_SEMANTIC_URL_LENGTH = 2048
MAX_SOURCE_CONSTRAINTS = 8

_PLAN_KEYS = frozenset(
    {
        "v",
        "r",
        "d",
        "i",
        "t",
        "s",
        "x",
        "f",
        "m",
        "c",
        "svc",
        "p",
        "u",
        "dc",
        "q",
    }
)
_TARGET_KEYS = frozenset({"k", "v"})
_CLARIFICATION_KEYS = frozenset({"s", "f"})

_EnumT = TypeVar("_EnumT", bound=Enum)


class SemanticPlanWireError(ValueError):
    """A semantic-plan payload violates the versioned wire contract."""


def semantic_plan_to_wire(plan: SemanticPlan) -> dict[str, object]:
    """Return the compact JSON-safe representation of ``plan``.

    Runtime type checks are intentional even though ``SemanticPlan`` is typed:
    a malformed object must not cross the same trust boundary used for model
    output merely because Python constructors do not enforce annotations.
    """

    if not isinstance(plan, SemanticPlan):
        raise SemanticPlanWireError("Expected a SemanticPlan instance.")
    if not isinstance(plan.target, TargetReference):
        raise SemanticPlanWireError("t must be a TargetReference value.")

    payload: dict[str, object] = {
        "v": SEMANTIC_PLAN_WIRE_VERSION,
        "r": _encode_enum(plan.route, SemanticPlanRoute, "r"),
        "d": _encode_enum(plan.domain, RequestDomain, "d"),
        "i": _encode_enum(plan.execution_intent, ExecutionIntent, "i"),
        "t": {
            "k": _encode_enum(plan.target.kind, TargetReferenceKind, "t.k"),
            "v": _optional_text(
                plan.target.value,
                "t.v",
                max_length=MAX_SEMANTIC_TEXT_LENGTH,
            ),
        },
        "s": _encode_sources(plan.source_constraints, "s", require_item=True),
        "x": _encode_sources(plan.excluded_sources, "x", require_item=False),
        "f": _encode_enum(plan.freshness, FreshnessRequirement, "f"),
        "m": _optional_text(plan.metric, "m"),
        "c": _optional_text(plan.concept, "c"),
        "svc": _optional_text(plan.service, "svc"),
        "p": _optional_text(plan.path, "p"),
        "u": _optional_text(
            plan.explicit_url,
            "u",
            max_length=MAX_SEMANTIC_URL_LENGTH,
        ),
        "dc": _encode_enum(
            plan.deterministic_compute,
            DeterministicComputeIntent,
            "dc",
        ),
        "q": {
            "s": _encode_enum(plan.clarification, ClarificationState, "q.s"),
            "f": _optional_text(plan.clarification_field, "q.f"),
        },
    }
    _ensure_payload_size(payload)
    return payload


def semantic_plan_from_wire(payload: object) -> SemanticPlan:
    """Parse a strict wire mapping without applying semantic defaults."""

    root = _exact_object(payload, _PLAN_KEYS, "plan")
    if type(root["v"]) is not int or root["v"] != SEMANTIC_PLAN_WIRE_VERSION:
        raise SemanticPlanWireError(
            f"v must be the integer {SEMANTIC_PLAN_WIRE_VERSION}."
        )

    target = _exact_object(root["t"], _TARGET_KEYS, "t")
    clarification = _exact_object(root["q"], _CLARIFICATION_KEYS, "q")

    plan = SemanticPlan(
        route=_parse_enum(SemanticPlanRoute, root["r"], "r"),
        domain=_parse_enum(RequestDomain, root["d"], "d"),
        execution_intent=_parse_enum(ExecutionIntent, root["i"], "i"),
        target=TargetReference(
            kind=_parse_enum(TargetReferenceKind, target["k"], "t.k"),
            value=_optional_text(
                target["v"],
                "t.v",
                max_length=MAX_SEMANTIC_TEXT_LENGTH,
            ),
        ),
        source_constraints=_parse_sources(root["s"], "s", require_item=True),
        excluded_sources=_parse_sources(root["x"], "x", require_item=False),
        freshness=_parse_enum(FreshnessRequirement, root["f"], "f"),
        metric=_optional_text(root["m"], "m"),
        concept=_optional_text(root["c"], "c"),
        service=_optional_text(root["svc"], "svc"),
        path=_optional_text(root["p"], "p"),
        explicit_url=_optional_text(
            root["u"],
            "u",
            max_length=MAX_SEMANTIC_URL_LENGTH,
        ),
        deterministic_compute=_parse_enum(
            DeterministicComputeIntent,
            root["dc"],
            "dc",
        ),
        clarification=_parse_enum(
            ClarificationState,
            clarification["s"],
            "q.s",
        ),
        clarification_field=_optional_text(clarification["f"], "q.f"),
    )
    _ensure_payload_size(root)
    return plan


def semantic_plan_to_json(plan: SemanticPlan) -> str:
    """Serialize a plan as compact UTF-8 JSON text."""

    return _compact_json(semantic_plan_to_wire(plan))


def semantic_plan_from_json(payload: str | bytes) -> SemanticPlan:
    """Parse bounded JSON and reject duplicate object keys."""

    if isinstance(payload, bytes):
        if len(payload) > MAX_SEMANTIC_PLAN_BYTES:
            raise SemanticPlanWireError("Semantic-plan payload exceeds 4096 bytes.")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SemanticPlanWireError("Semantic-plan payload is not UTF-8.") from exc
    elif isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_SEMANTIC_PLAN_BYTES:
            raise SemanticPlanWireError("Semantic-plan payload exceeds 4096 bytes.")
        text = payload
    else:
        raise SemanticPlanWireError("Semantic-plan JSON must be text or bytes.")

    try:
        decoded = json.loads(text, object_pairs_hook=_object_without_duplicate_keys)
    except JSONDecodeError as exc:
        raise SemanticPlanWireError("Semantic-plan payload is not valid JSON.") from exc
    return semantic_plan_from_wire(decoded)


def semantic_plan_json_schema() -> dict[str, object]:
    """Return the provider-neutral JSON Schema for wire version 1."""

    nullable_text = _nullable_text_schema(MAX_SEMANTIC_TEXT_LENGTH)
    source_items = {"type": "string", "enum": _enum_values(SourceConstraint)}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OrionSemanticPlanV1",
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_PLAN_KEYS),
        "properties": {
            "v": {"type": "integer", "enum": [SEMANTIC_PLAN_WIRE_VERSION]},
            "r": {"type": "string", "enum": _enum_values(SemanticPlanRoute)},
            "d": {"type": "string", "enum": _enum_values(RequestDomain)},
            "i": {"type": "string", "enum": _enum_values(ExecutionIntent)},
            "t": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(_TARGET_KEYS),
                "properties": {
                    "k": {
                        "type": "string",
                        "enum": _enum_values(TargetReferenceKind),
                    },
                    "v": nullable_text,
                },
            },
            "s": {
                "type": "array",
                "items": source_items,
                "minItems": 1,
                "maxItems": MAX_SOURCE_CONSTRAINTS,
                "uniqueItems": True,
            },
            "x": {
                "type": "array",
                "items": source_items,
                "maxItems": MAX_SOURCE_CONSTRAINTS,
                "uniqueItems": True,
            },
            "f": {
                "type": "string",
                "enum": _enum_values(FreshnessRequirement),
            },
            "m": nullable_text,
            "c": nullable_text,
            "svc": nullable_text,
            "p": nullable_text,
            "u": _nullable_text_schema(MAX_SEMANTIC_URL_LENGTH),
            "dc": {
                "type": "string",
                "enum": _enum_values(DeterministicComputeIntent),
            },
            "q": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(_CLARIFICATION_KEYS),
                "properties": {
                    "s": {
                        "type": "string",
                        "enum": _enum_values(ClarificationState),
                    },
                    "f": nullable_text,
                },
            },
        },
    }


def _exact_object(
    value: object,
    expected_keys: frozenset[str],
    field: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SemanticPlanWireError(f"{field} must be an object.")
    actual_keys = set(value)
    unknown = actual_keys - expected_keys
    missing = expected_keys - actual_keys
    if unknown:
        raise SemanticPlanWireError(
            f"{field} contains unknown fields: {', '.join(sorted(map(str, unknown)))}."
        )
    if missing:
        raise SemanticPlanWireError(
            f"{field} is missing fields: {', '.join(sorted(missing))}."
        )
    return value


def _encode_enum(value: _EnumT, enum_type: type[_EnumT], field: str) -> str:
    if not isinstance(value, enum_type):
        raise SemanticPlanWireError(f"{field} must be a {enum_type.__name__} value.")
    return value.name.casefold()


def _parse_enum(
    enum_type: type[_EnumT],
    value: object,
    field: str,
) -> _EnumT:
    if not isinstance(value, str):
        raise SemanticPlanWireError(f"{field} must be a string enum value.")
    members = {item.name.casefold(): item for item in enum_type}
    try:
        return members[value]
    except KeyError as exc:
        raise SemanticPlanWireError(f"{field} has an unknown enum value.") from exc


def _encode_sources(
    values: object,
    field: str,
    *,
    require_item: bool,
) -> list[str]:
    if not isinstance(values, tuple):
        raise SemanticPlanWireError(f"{field} must be a tuple of SourceConstraint.")
    encoded = [_encode_enum(value, SourceConstraint, f"{field}[]") for value in values]
    _validate_source_items(encoded, field, require_item=require_item)
    return encoded


def _parse_sources(
    value: object,
    field: str,
    *,
    require_item: bool,
) -> tuple[SourceConstraint, ...]:
    if not isinstance(value, list):
        raise SemanticPlanWireError(f"{field} must be an array.")
    parsed = tuple(_parse_enum(SourceConstraint, item, f"{field}[]") for item in value)
    _validate_source_items(
        [item.name.casefold() for item in parsed],
        field,
        require_item=require_item,
    )
    return parsed


def _validate_source_items(
    values: list[str],
    field: str,
    *,
    require_item: bool,
) -> None:
    if require_item and not values:
        raise SemanticPlanWireError(f"{field} must contain at least one item.")
    if len(values) > MAX_SOURCE_CONSTRAINTS:
        raise SemanticPlanWireError(
            f"{field} must contain at most {MAX_SOURCE_CONSTRAINTS} items."
        )
    if len(set(values)) != len(values):
        raise SemanticPlanWireError(f"{field} must not contain duplicate items.")


def _optional_text(
    value: object,
    field: str,
    *,
    max_length: int = MAX_SEMANTIC_TEXT_LENGTH,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SemanticPlanWireError(f"{field} must be a string or null.")
    if not value or value != value.strip():
        raise SemanticPlanWireError(f"{field} must be non-empty trimmed text or null.")
    if len(value) > max_length:
        raise SemanticPlanWireError(
            f"{field} must contain at most {max_length} characters."
        )
    if any(ord(character) < 32 for character in value):
        raise SemanticPlanWireError(f"{field} must not contain control characters.")
    return value


def _ensure_payload_size(payload: dict[str, object]) -> None:
    if len(_compact_json(payload).encode("utf-8")) > MAX_SEMANTIC_PLAN_BYTES:
        raise SemanticPlanWireError("Semantic-plan payload exceeds 4096 bytes.")


def _compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SemanticPlanWireError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [value.name.casefold() for value in enum_type]


def _nullable_text_schema(max_length: int) -> dict[str, object]:
    return {
        "anyOf": [
            {"type": "string", "minLength": 1, "maxLength": max_length},
            {"type": "null"},
        ]
    }


__all__ = [
    "MAX_SEMANTIC_PLAN_BYTES",
    "SEMANTIC_PLAN_WIRE_VERSION",
    "SemanticPlanWireError",
    "semantic_plan_from_json",
    "semantic_plan_from_wire",
    "semantic_plan_json_schema",
    "semantic_plan_to_json",
    "semantic_plan_to_wire",
]
