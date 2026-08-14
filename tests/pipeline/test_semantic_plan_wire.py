from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal

import pytest

from src.pipeline.basic_calculator import CalculatorOperation, CalculatorRequest
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
from src.pipeline.semantic_plan_wire import (
    MAX_SEMANTIC_PLAN_BYTES,
    SEMANTIC_PLAN_WIRE_VERSION,
    SemanticPlanWireError,
    semantic_plan_from_json,
    semantic_plan_from_wire,
    semantic_plan_json_schema,
    semantic_plan_to_json,
    semantic_plan_to_wire,
)


@pytest.fixture
def rich_plan() -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "monitor"),
        source_constraints=(SourceConstraint.GRAFANA,),
        excluded_sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.REAL_TIME,
        metric="cpu.usage_percent",
        concept="cpu",
        service="nginx",
        path="/var/log/nginx/access.log",
        explicit_url="https://example.com/status",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
        clarification_field=None,
    )


def test_wire_round_trip_is_lossless_and_compact(rich_plan: SemanticPlan) -> None:
    wire = semantic_plan_to_wire(rich_plan)
    encoded = semantic_plan_to_json(rich_plan)

    assert semantic_plan_from_wire(wire) == rich_plan
    assert semantic_plan_from_json(encoded) == rich_plan
    assert semantic_plan_from_json(encoded.encode()) == rich_plan
    assert len(encoded.encode()) < MAX_SEMANTIC_PLAN_BYTES
    assert " " not in encoded
    assert set(wire) == {
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
    }


def test_default_plan_round_trips_without_becoming_executable() -> None:
    parsed = semantic_plan_from_json(semantic_plan_to_json(SemanticPlan()))

    assert parsed == SemanticPlan()
    assert parsed.route is SemanticPlanRoute.UNSPECIFIED
    assert parsed.target.kind is TargetReferenceKind.UNSPECIFIED
    assert parsed.source_constraints == (SourceConstraint.UNSPECIFIED,)


def test_structured_calculation_round_trips_with_exact_decimal_operands() -> None:
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        deterministic_compute=DeterministicComputeIntent.REQUIRED,
        calculation=CalculatorRequest(
            CalculatorOperation.AVERAGE,
            values=(Decimal("20"), Decimal("40"), Decimal("60")),
        ),
        clarification=ClarificationState.NOT_REQUIRED,
    )

    wire = semantic_plan_to_wire(plan)
    parsed = semantic_plan_from_wire(wire)

    assert parsed == plan
    assert wire["calc"]["values"] == ["20", "40", "60"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update({"raw_command": "id"}), "unknown fields"),
        (lambda value: value.pop("r"), "missing fields"),
        (lambda value: value.update({"r": "invented"}), "unknown enum"),
        (lambda value: value.update({"r": "DIRECT_ANSWER"}), "unknown enum"),
        (lambda value: value.update({"d": 1}), "string enum"),
        (lambda value: value.update({"v": "1"}), "integer 1"),
        (lambda value: value.update({"s": "grafana"}), "must be an array"),
        (lambda value: value.update({"s": []}), "at least one"),
        (
            lambda value: value.update({"s": ["grafana", "grafana"]}),
            "duplicate",
        ),
        (lambda value: value.update({"t": "monitor"}), "must be an object"),
        (
            lambda value: value.update(
                {"t": {"k": "explicit", "v": "monitor", "resolved": True}}
            ),
            "unknown fields",
        ),
        (
            lambda value: value.update({"q": {"s": "required"}}),
            "missing fields",
        ),
    ],
)
def test_malformed_wire_payloads_fail_explicitly(
    rich_plan: SemanticPlan,
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    payload = semantic_plan_to_wire(rich_plan)
    mutate(payload)

    with pytest.raises(SemanticPlanWireError, match=message):
        semantic_plan_from_wire(payload)


def test_invalid_text_and_oversized_payloads_are_rejected(
    rich_plan: SemanticPlan,
) -> None:
    payload = semantic_plan_to_wire(rich_plan)
    payload["c"] = " untrimmed "
    with pytest.raises(SemanticPlanWireError, match="trimmed"):
        semantic_plan_from_wire(payload)

    oversized = "{" + (" " * MAX_SEMANTIC_PLAN_BYTES) + "}"
    with pytest.raises(SemanticPlanWireError, match="exceeds"):
        semantic_plan_from_json(oversized)


def test_serializer_rejects_runtime_values_that_violate_annotations() -> None:
    malformed = SemanticPlan(target="monitor")  # type: ignore[arg-type]

    with pytest.raises(SemanticPlanWireError, match="TargetReference"):
        semantic_plan_to_wire(malformed)


def test_json_parser_rejects_invalid_root_and_duplicate_fields(
    rich_plan: SemanticPlan,
) -> None:
    with pytest.raises(SemanticPlanWireError, match="valid JSON"):
        semantic_plan_from_json("{")
    with pytest.raises(SemanticPlanWireError, match="must be an object"):
        semantic_plan_from_json("[]")

    encoded = semantic_plan_to_json(rich_plan)
    duplicate = encoded.replace(
        f'"v":{SEMANTIC_PLAN_WIRE_VERSION}',
        f'"v":{SEMANTIC_PLAN_WIRE_VERSION},"v":{SEMANTIC_PLAN_WIRE_VERSION}',
        1,
    )
    with pytest.raises(SemanticPlanWireError, match="Duplicate JSON field"):
        semantic_plan_from_json(duplicate)


def test_schema_matches_strict_wire_contract() -> None:
    schema = semantic_plan_json_schema()
    properties = schema["properties"]

    assert isinstance(properties, dict)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(properties)
    assert properties["v"]["enum"] == [SEMANTIC_PLAN_WIRE_VERSION]
    assert properties["t"]["additionalProperties"] is False
    assert properties["q"]["additionalProperties"] is False
    assert properties["s"]["minItems"] == 1
    assert properties["s"]["uniqueItems"] is True
    assert "capability_assisted" in properties["r"]["enum"]
    assert "unspecified" in properties["d"]["enum"]
    assert "unknown" in properties["i"]["enum"]
    assert json.dumps(schema)


def test_wire_contract_has_no_execution_or_evidence_fields(
    rich_plan: SemanticPlan,
) -> None:
    encoded = semantic_plan_to_json(rich_plan)

    for forbidden in (
        "command",
        "credential",
        "evidence",
        "reasoning",
        "tool_schema",
    ):
        assert forbidden not in encoded
