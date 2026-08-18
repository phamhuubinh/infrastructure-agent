"""Strict, bounded wire contract for :mod:`semantic_plan`.

The compact versioned mapping is the only model/harness exchange shape.  It
uses short stable keys to keep planner input/output small, rejects missing or
unknown fields, and never coerces malformed data into executable defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from json import JSONDecodeError
from typing import TypeVar

from src.pipeline.basic_calculator import (
    CalculatorDurationUnit,
    CalculatorOperation,
    CalculatorRateUnit,
    CalculatorRequest,
)
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    MAX_SEMANTIC_SUBPLANS,
    MAX_SUBPLAN_DEPENDENCIES,
    MAX_SUBPLAN_REQUEST_LENGTH,
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
    SemanticSubplan,
    TargetReference,
    TargetReferenceKind,
)

SEMANTIC_PLAN_WIRE_VERSION = 1
MAX_SEMANTIC_PLAN_BYTES = 4096
MAX_SEMANTIC_TEXT_LENGTH = 256
MAX_SEMANTIC_URL_LENGTH = 2048
MAX_SOURCE_CONSTRAINTS = 8
MAX_CALCULATOR_VALUES = 32

PLANNER_OUTPUT_WIRE_VERSION = 1
MAX_PLANNER_FINAL_ANSWER_LENGTH = 512

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
        "calc",
        "q",
        "sp",
    }
)
_TARGET_KEYS = frozenset({"k", "v"})
_CLARIFICATION_KEYS = frozenset({"s", "f"})
_PLANNER_OUTPUT_KEYS = frozenset({"v", "p", "a"})
_SUBPLAN_KEYS = frozenset({"r", "p", "d"})
_CALCULATION_KEYS = frozenset(
    {
        "op",
        "values",
        "l",
        "r",
        "base",
        "pct",
        "tasks",
        "workers",
        "duration",
        "duration_unit",
        "rate",
        "rate_unit",
        "target_rate_unit",
        "unit",
    }
)

_EnumT = TypeVar("_EnumT", bound=Enum)


class SemanticPlanWireError(ValueError):
    """A semantic-plan payload violates the versioned wire contract."""


@dataclass(frozen=True, slots=True)
class PlannerWireOutput:
    """One validated planner output: a plan plus an optional final answer.

    ``final_answer`` is deliberately outside ``SemanticPlan``: answer prose
    is never part of execution-authoritative semantics.  The harness gate,
    not the planner, decides whether the text may be delivered.
    """

    plan: SemanticPlan
    final_answer: str | None


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
        "calc": _encode_calculation(plan.calculation),
        "q": {
            "s": _encode_enum(plan.clarification, ClarificationState, "q.s"),
            "f": _optional_text(plan.clarification_field, "q.f"),
        },
        "sp": _encode_subplans(plan),
    }
    _ensure_payload_size(payload)
    return payload


def semantic_plan_from_wire(payload: object) -> SemanticPlan:
    """Parse a strict wire mapping without applying semantic defaults."""

    root = _plan_object(payload, "plan")
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
        calculation=_parse_calculation(root["calc"]),
        clarification=_parse_enum(
            ClarificationState,
            clarification["s"],
            "q.s",
        ),
        clarification_field=_optional_text(clarification["f"], "q.f"),
        subplans=_parse_subplans(root["sp"]),
    )
    _validate_subplan_container(plan)
    _ensure_payload_size(root)
    return plan


def semantic_plan_to_json(plan: SemanticPlan) -> str:
    """Serialize a plan as compact UTF-8 JSON text."""

    return _compact_json(semantic_plan_to_wire(plan))


def semantic_plan_from_json(payload: str | bytes) -> SemanticPlan:
    """Parse bounded JSON and reject duplicate object keys."""

    return semantic_plan_from_wire(_decode_payload_json(payload))


def planner_output_to_wire(
    plan: SemanticPlan,
    final_answer: str | None = None,
) -> dict[str, object]:
    """Return the compact planner-output envelope for ``plan``.

    ``final_answer`` is optional bounded answer prose for an eligible
    DIRECT_ANSWER plan.  A non-null answer on any other route is a
    mismatched payload and is rejected fail-closed.
    """

    if not isinstance(plan, SemanticPlan):
        raise SemanticPlanWireError("Expected a SemanticPlan instance.")
    answer = _optional_text(
        final_answer,
        "a",
        max_length=MAX_PLANNER_FINAL_ANSWER_LENGTH,
    )
    _validate_final_answer_route(plan, answer)
    payload: dict[str, object] = {
        "v": PLANNER_OUTPUT_WIRE_VERSION,
        "p": semantic_plan_to_wire(plan),
        "a": answer,
    }
    _ensure_payload_size(payload)
    return payload


def planner_output_from_wire(payload: object) -> PlannerWireOutput:
    """Parse one planner output: the envelope or a legacy plan-only payload.

    The envelope is the current model/harness shape.  A payload without the
    answer key is parsed as a legacy flat semantic plan for backward
    compatibility with pre-envelope providers; it carries no final answer.
    """

    if not isinstance(payload, dict):
        raise SemanticPlanWireError("Planner output must be an object.")
    if "a" in payload:
        return _parse_planner_output_envelope(payload)
    return PlannerWireOutput(
        plan=semantic_plan_from_wire(payload),
        final_answer=None,
    )


def planner_output_to_json(
    plan: SemanticPlan,
    final_answer: str | None = None,
) -> str:
    """Serialize a planner output as compact UTF-8 JSON text."""

    return _compact_json(planner_output_to_wire(plan, final_answer))


def planner_output_from_json(payload: str | bytes) -> PlannerWireOutput:
    """Parse bounded planner-output JSON and reject duplicate object keys."""

    return planner_output_from_wire(_decode_payload_json(payload))


def semantic_plan_json_schema() -> dict[str, object]:
    """Return the provider-neutral JSON Schema for wire version 1."""

    schema = _semantic_plan_schema(allow_subplans=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "OrionSemanticPlanV1"
    return schema


def _semantic_plan_schema(*, allow_subplans: bool) -> dict[str, object]:
    nullable_text = _nullable_text_schema(MAX_SEMANTIC_TEXT_LENGTH)
    source_items = {"type": "string", "enum": _enum_values(SourceConstraint)}
    properties: dict[str, object] = {
        "v": {"type": "integer", "enum": [SEMANTIC_PLAN_WIRE_VERSION]},
        "r": {"type": "string", "enum": _enum_values(SemanticPlanRoute)},
        "d": {"type": "string", "enum": _enum_values(RequestDomain)},
        "i": {"type": "string", "enum": _enum_values(ExecutionIntent)},
        "t": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(_TARGET_KEYS),
            "properties": {
                "k": {"type": "string", "enum": _enum_values(TargetReferenceKind)},
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
        "f": {"type": "string", "enum": _enum_values(FreshnessRequirement)},
        "m": nullable_text,
        "c": nullable_text,
        "svc": nullable_text,
        "p": nullable_text,
        "u": _nullable_text_schema(MAX_SEMANTIC_URL_LENGTH),
        "dc": {
            "type": "string",
            "enum": _enum_values(DeterministicComputeIntent),
        },
        "calc": {"anyOf": [_calculation_schema(), {"type": "null"}]},
        "q": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(_CLARIFICATION_KEYS),
            "properties": {
                "s": {"type": "string", "enum": _enum_values(ClarificationState)},
                "f": nullable_text,
            },
        },
        "sp": (
            _semantic_subplan_schema()
            if allow_subplans
            else {"type": "array", "maxItems": 0}
        ),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_PLAN_KEYS),
        "properties": properties,
    }


def _semantic_subplan_schema() -> dict[str, object]:
    return {
        "type": "array",
        "maxItems": MAX_SEMANTIC_SUBPLANS,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(_SUBPLAN_KEYS),
            "properties": {
                "r": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_SUBPLAN_REQUEST_LENGTH,
                },
                "p": _semantic_plan_schema(allow_subplans=False),
                "d": {
                    "type": "array",
                    "items": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": MAX_SEMANTIC_SUBPLANS - 1,
                    },
                    "maxItems": MAX_SUBPLAN_DEPENDENCIES,
                    "uniqueItems": True,
                },
            },
        },
    }


def planner_output_json_schema() -> dict[str, object]:
    """Return the provider-neutral JSON Schema for the planner-output envelope."""

    plan_schema = semantic_plan_json_schema()
    plan_schema.pop("$schema", None)
    plan_schema.pop("title", None)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OrionPlannerOutputV1",
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_PLANNER_OUTPUT_KEYS),
        "properties": {
            "v": {"type": "integer", "enum": [PLANNER_OUTPUT_WIRE_VERSION]},
            "p": plan_schema,
            "a": {
                "anyOf": [
                    {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_PLANNER_FINAL_ANSWER_LENGTH,
                    },
                    {"type": "null"},
                ]
            },
        },
    }


def _plan_object(value: object, field: str) -> dict[str, object]:
    """Parse a plan object while accepting pre-subplan v1 payloads."""

    if not isinstance(value, dict):
        raise SemanticPlanWireError(f"{field} must be an object.")
    actual_keys = set(value)
    unknown = actual_keys - _PLAN_KEYS
    missing = (_PLAN_KEYS - {"sp"}) - actual_keys
    if unknown:
        raise SemanticPlanWireError(
            f"{field} contains unknown fields: {', '.join(sorted(map(str, unknown)))}."
        )
    if missing:
        raise SemanticPlanWireError(
            f"{field} is missing fields: {', '.join(sorted(missing))}."
        )
    root = dict(value)
    root.setdefault("sp", [])
    return root


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


def _encode_subplans(plan: SemanticPlan) -> list[dict[str, object]]:
    _validate_subplan_container(plan)
    encoded: list[dict[str, object]] = []
    for index, item in enumerate(plan.subplans):
        request = _optional_text(
            item.request,
            f"sp[{index}].r",
            max_length=MAX_SUBPLAN_REQUEST_LENGTH,
        )
        assert request is not None
        encoded.append(
            {
                "r": request,
                "p": semantic_plan_to_wire(item.plan),
                "d": list(item.depends_on),
            }
        )
    return encoded


def _parse_subplans(value: object) -> tuple[SemanticSubplan, ...]:
    if not isinstance(value, list):
        raise SemanticPlanWireError("sp must be an array.")
    if len(value) > MAX_SEMANTIC_SUBPLANS:
        raise SemanticPlanWireError(
            f"sp must contain at most {MAX_SEMANTIC_SUBPLANS} items."
        )
    parsed: list[SemanticSubplan] = []
    for index, raw in enumerate(value):
        item = _exact_object(raw, _SUBPLAN_KEYS, f"sp[{index}]")
        request = _optional_text(
            item["r"],
            f"sp[{index}].r",
            max_length=MAX_SUBPLAN_REQUEST_LENGTH,
        )
        assert request is not None
        parsed.append(
            SemanticSubplan(
                request=request,
                plan=semantic_plan_from_wire(item["p"]),
                depends_on=_parse_subplan_dependencies(item["d"], index),
            )
        )
    return tuple(parsed)


def _parse_subplan_dependencies(value: object, index: int) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise SemanticPlanWireError(f"sp[{index}].d must be an array.")
    if len(value) > MAX_SUBPLAN_DEPENDENCIES:
        raise SemanticPlanWireError(
            f"sp[{index}].d must contain at most {MAX_SUBPLAN_DEPENDENCIES} items."
        )
    if any(type(item) is not int for item in value):
        raise SemanticPlanWireError(f"sp[{index}].d must contain integer indexes.")
    if len(set(value)) != len(value):
        raise SemanticPlanWireError(f"sp[{index}].d must not contain duplicates.")
    if any(item < 0 or item >= index for item in value):
        raise SemanticPlanWireError(
            f"sp[{index}].d may reference earlier subplans only."
        )
    return tuple(value)


def _validate_subplan_container(plan: SemanticPlan) -> None:
    subplans = plan.subplans
    if not isinstance(subplans, tuple) or any(
        not isinstance(item, SemanticSubplan) for item in subplans
    ):
        raise SemanticPlanWireError("sp must be a tuple of SemanticSubplan values.")
    if not subplans:
        if plan.route is SemanticPlanRoute.MULTI_INTENT:
            raise SemanticPlanWireError("multi_intent requires at least two subplans.")
        return
    if plan.route is not SemanticPlanRoute.MULTI_INTENT:
        raise SemanticPlanWireError("sp is only allowed for multi_intent plans.")
    if len(subplans) < 2 or len(subplans) > MAX_SEMANTIC_SUBPLANS:
        raise SemanticPlanWireError(
            f"multi_intent requires 2-{MAX_SEMANTIC_SUBPLANS} subplans."
        )
    for index, item in enumerate(subplans):
        if not isinstance(item.plan, SemanticPlan):
            raise SemanticPlanWireError(f"sp[{index}].p must be a SemanticPlan.")
        if item.plan.subplans:
            raise SemanticPlanWireError("Nested semantic subplans are not allowed.")
        if item.plan.route not in {
            SemanticPlanRoute.DIRECT_ANSWER,
            SemanticPlanRoute.CAPABILITY_ASSISTED,
        }:
            raise SemanticPlanWireError(
                f"sp[{index}] must use direct_answer or capability_assisted."
            )
        _optional_text(
            item.request,
            f"sp[{index}].r",
            max_length=MAX_SUBPLAN_REQUEST_LENGTH,
        )
        if not isinstance(item.depends_on, tuple):
            raise SemanticPlanWireError(f"sp[{index}].d must be a tuple of indexes.")
        _parse_subplan_dependencies(list(item.depends_on), index)
        if SourceConstraint.UNSPECIFIED in item.plan.source_constraints:
            raise SemanticPlanWireError(
                f"sp[{index}] must state source semantics explicitly."
            )
        if item.plan.freshness in {
            FreshnessRequirement.UNSPECIFIED,
            FreshnessRequirement.UNKNOWN,
        }:
            raise SemanticPlanWireError(
                f"sp[{index}] must state freshness semantics explicitly."
            )
        if (
            item.plan.route is SemanticPlanRoute.CAPABILITY_ASSISTED
            and item.plan.domain is RequestDomain.ENVIRONMENT
            and item.plan.target.kind
            not in {TargetReferenceKind.EXPLICIT, TargetReferenceKind.INHERITED}
        ):
            raise SemanticPlanWireError(
                f"sp[{index}] environment execution requires an explicit target."
            )


def _encode_calculation(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, CalculatorRequest):
        raise SemanticPlanWireError("calc must be a CalculatorRequest or null.")
    if len(value.values) > MAX_CALCULATOR_VALUES:
        raise SemanticPlanWireError(
            f"calc.values must contain at most {MAX_CALCULATOR_VALUES} items."
        )
    return {
        "op": _encode_enum(value.operation, CalculatorOperation, "calc.op"),
        "values": [_decimal_text(item, "calc.values[]") for item in value.values],
        "l": _optional_decimal_text(value.left, "calc.l"),
        "r": _optional_decimal_text(value.right, "calc.r"),
        "base": _optional_decimal_text(value.base_value, "calc.base"),
        "pct": _optional_decimal_text(value.percent, "calc.pct"),
        "tasks": _optional_decimal_text(value.total_tasks, "calc.tasks"),
        "workers": _optional_decimal_text(value.workers, "calc.workers"),
        "duration": _optional_decimal_text(value.duration, "calc.duration"),
        "duration_unit": _optional_enum_text(
            value.duration_unit,
            CalculatorDurationUnit,
            "calc.duration_unit",
        ),
        "rate": _optional_decimal_text(value.rate_value, "calc.rate"),
        "rate_unit": _optional_enum_text(
            value.rate_unit,
            CalculatorRateUnit,
            "calc.rate_unit",
        ),
        "target_rate_unit": _optional_enum_text(
            value.target_rate_unit,
            CalculatorRateUnit,
            "calc.target_rate_unit",
        ),
        "unit": _optional_text(value.unit, "calc.unit", max_length=64),
    }


def _parse_calculation(value: object) -> CalculatorRequest | None:
    if value is None:
        return None
    root = _exact_object(value, _CALCULATION_KEYS, "calc")
    raw_values = root["values"]
    if not isinstance(raw_values, list):
        raise SemanticPlanWireError("calc.values must be an array.")
    if len(raw_values) > MAX_CALCULATOR_VALUES:
        raise SemanticPlanWireError(
            f"calc.values must contain at most {MAX_CALCULATOR_VALUES} items."
        )
    return CalculatorRequest(
        operation=_parse_enum(CalculatorOperation, root["op"], "calc.op"),
        values=tuple(_parse_decimal(item, "calc.values[]") for item in raw_values),
        left=_optional_decimal(root["l"], "calc.l"),
        right=_optional_decimal(root["r"], "calc.r"),
        base_value=_optional_decimal(root["base"], "calc.base"),
        percent=_optional_decimal(root["pct"], "calc.pct"),
        total_tasks=_optional_decimal(root["tasks"], "calc.tasks"),
        workers=_optional_decimal(root["workers"], "calc.workers"),
        duration=_optional_decimal(root["duration"], "calc.duration"),
        duration_unit=_optional_enum(
            CalculatorDurationUnit,
            root["duration_unit"],
            "calc.duration_unit",
        ),
        rate_value=_optional_decimal(root["rate"], "calc.rate"),
        rate_unit=_optional_enum(
            CalculatorRateUnit,
            root["rate_unit"],
            "calc.rate_unit",
        ),
        target_rate_unit=_optional_enum(
            CalculatorRateUnit,
            root["target_rate_unit"],
            "calc.target_rate_unit",
        ),
        unit=_optional_text(root["unit"], "calc.unit", max_length=64),
    )


def _decimal_text(value: object, field: str) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise SemanticPlanWireError(f"{field} must be a finite Decimal value.")
    return str(value)


def _optional_decimal_text(value: object, field: str) -> str | None:
    return None if value is None else _decimal_text(value, field)


def _parse_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise SemanticPlanWireError(f"{field} must be a bounded decimal string.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise SemanticPlanWireError(f"{field} must be a decimal string.") from exc
    if not parsed.is_finite():
        raise SemanticPlanWireError(f"{field} must be finite.")
    return parsed


def _optional_decimal(value: object, field: str) -> Decimal | None:
    return None if value is None else _parse_decimal(value, field)


def _optional_enum_text(
    value: _EnumT | None,
    enum_type: type[_EnumT],
    field: str,
) -> str | None:
    return None if value is None else _encode_enum(value, enum_type, field)


def _optional_enum(
    enum_type: type[_EnumT],
    value: object,
    field: str,
) -> _EnumT | None:
    return None if value is None else _parse_enum(enum_type, value, field)


def _calculation_schema() -> dict[str, object]:
    nullable_decimal = {
        "anyOf": [
            {"type": "string", "minLength": 1, "maxLength": 64},
            {"type": "null"},
        ]
    }
    nullable_duration_unit = {
        "anyOf": [
            {"type": "string", "enum": _enum_values(CalculatorDurationUnit)},
            {"type": "null"},
        ]
    }
    nullable_rate_unit = {
        "anyOf": [
            {"type": "string", "enum": _enum_values(CalculatorRateUnit)},
            {"type": "null"},
        ]
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_CALCULATION_KEYS),
        "properties": {
            "op": {"type": "string", "enum": _enum_values(CalculatorOperation)},
            "values": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 64},
                "maxItems": MAX_CALCULATOR_VALUES,
            },
            "l": nullable_decimal,
            "r": nullable_decimal,
            "base": nullable_decimal,
            "pct": nullable_decimal,
            "tasks": nullable_decimal,
            "workers": nullable_decimal,
            "duration": nullable_decimal,
            "duration_unit": nullable_duration_unit,
            "rate": nullable_decimal,
            "rate_unit": nullable_rate_unit,
            "target_rate_unit": nullable_rate_unit,
            "unit": _nullable_text_schema(64),
        },
    }


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


def _parse_planner_output_envelope(
    payload: dict[str, object],
) -> PlannerWireOutput:
    root = _exact_object(payload, _PLANNER_OUTPUT_KEYS, "planner output")
    if type(root["v"]) is not int or root["v"] != PLANNER_OUTPUT_WIRE_VERSION:
        raise SemanticPlanWireError(
            f"v must be the integer {PLANNER_OUTPUT_WIRE_VERSION}."
        )
    plan = semantic_plan_from_wire(root["p"])
    final_answer = _optional_text(
        root["a"],
        "a",
        max_length=MAX_PLANNER_FINAL_ANSWER_LENGTH,
    )
    _validate_final_answer_route(plan, final_answer)
    _ensure_payload_size(root)
    return PlannerWireOutput(plan=plan, final_answer=final_answer)


def _validate_final_answer_route(
    plan: SemanticPlan,
    final_answer: str | None,
) -> None:
    if final_answer is not None and plan.route is not SemanticPlanRoute.DIRECT_ANSWER:
        raise SemanticPlanWireError(
            "a is only allowed when the plan route is direct_answer."
        )


def _decode_payload_json(payload: str | bytes) -> object:
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
        return json.loads(text, object_pairs_hook=_object_without_duplicate_keys)
    except JSONDecodeError as exc:
        raise SemanticPlanWireError("Semantic-plan payload is not valid JSON.") from exc


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
    "MAX_PLANNER_FINAL_ANSWER_LENGTH",
    "MAX_SEMANTIC_PLAN_BYTES",
    "PLANNER_OUTPUT_WIRE_VERSION",
    "SEMANTIC_PLAN_WIRE_VERSION",
    "PlannerWireOutput",
    "SemanticPlanWireError",
    "planner_output_from_json",
    "planner_output_from_wire",
    "planner_output_json_schema",
    "planner_output_to_json",
    "planner_output_to_wire",
    "semantic_plan_from_json",
    "semantic_plan_from_wire",
    "semantic_plan_json_schema",
    "semantic_plan_to_json",
    "semantic_plan_to_wire",
]
