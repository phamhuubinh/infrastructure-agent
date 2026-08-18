from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
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
    MAX_PLANNER_FINAL_ANSWER_LENGTH,
    MAX_SEMANTIC_PLAN_BYTES,
    PLANNER_OUTPUT_WIRE_VERSION,
    SEMANTIC_PLAN_WIRE_VERSION,
    PlannerWireOutput,
    SemanticPlanWireError,
    planner_output_from_json,
    planner_output_from_wire,
    planner_output_json_schema,
    planner_output_to_json,
    planner_output_to_wire,
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
        "sp",
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


@pytest.fixture
def direct_answer_plan(rich_plan: SemanticPlan) -> SemanticPlan:
    return replace(
        rich_plan,
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        target=TargetReference(),
        source_constraints=(SourceConstraint.ANY,),
        excluded_sources=(),
        freshness=FreshnessRequirement.STABLE,
        metric=None,
        service=None,
        path=None,
        explicit_url=None,
    )


def test_planner_output_round_trip_carries_bounded_final_answer(
    direct_answer_plan: SemanticPlan,
) -> None:
    answer = "Xin chào! Tôi có thể giúp gì cho bạn?"
    wire = planner_output_to_wire(direct_answer_plan, answer)

    assert set(wire) == {"v", "p", "a"}
    assert wire["v"] == PLANNER_OUTPUT_WIRE_VERSION
    assert wire["a"] == answer

    parsed = planner_output_from_wire(wire)
    assert isinstance(parsed, PlannerWireOutput)
    assert parsed.plan == direct_answer_plan
    assert parsed.final_answer == answer

    encoded = planner_output_to_json(direct_answer_plan, answer)
    assert ": " not in encoded
    assert ", " not in encoded
    assert len(encoded.encode()) < MAX_SEMANTIC_PLAN_BYTES
    assert planner_output_from_json(encoded) == parsed
    assert planner_output_from_json(encoded.encode()) == parsed


def test_planner_output_without_answer_round_trips(
    direct_answer_plan: SemanticPlan,
) -> None:
    parsed = planner_output_from_wire(planner_output_to_wire(direct_answer_plan))

    assert parsed.plan == direct_answer_plan
    assert parsed.final_answer is None


def test_planner_output_rejects_final_answer_on_non_direct_route(
    rich_plan: SemanticPlan,
) -> None:
    with pytest.raises(SemanticPlanWireError, match="direct_answer"):
        planner_output_to_wire(rich_plan, "hello")

    mismatched = planner_output_to_wire(
        replace(rich_plan, route=SemanticPlanRoute.DIRECT_ANSWER),
        "hello",
    )
    mismatched["p"] = semantic_plan_to_wire(rich_plan)
    with pytest.raises(SemanticPlanWireError, match="direct_answer"):
        planner_output_from_wire(mismatched)


@pytest.mark.parametrize(
    "answer",
    (
        "",
        " untrimmed ",
        "has\ncontrol",
        "x" * (MAX_PLANNER_FINAL_ANSWER_LENGTH + 1),
    ),
)
def test_planner_output_rejects_malformed_final_answer(
    direct_answer_plan: SemanticPlan,
    answer: str,
) -> None:
    with pytest.raises(SemanticPlanWireError):
        planner_output_to_wire(direct_answer_plan, answer)


def test_legacy_plan_only_payload_still_parses_as_planner_output(
    direct_answer_plan: SemanticPlan,
) -> None:
    parsed = planner_output_from_wire(semantic_plan_to_wire(direct_answer_plan))

    assert parsed.plan == direct_answer_plan
    assert parsed.final_answer is None

    parsed_json = planner_output_from_json(semantic_plan_to_json(direct_answer_plan))
    assert parsed_json == parsed


def test_planner_output_rejects_malformed_envelopes() -> None:
    with pytest.raises(SemanticPlanWireError, match="must be an object"):
        planner_output_from_wire([])
    with pytest.raises(SemanticPlanWireError, match="must be an object"):
        planner_output_from_json("[]")
    with pytest.raises(SemanticPlanWireError, match="valid JSON"):
        planner_output_from_json("{")

    envelope = {"v": PLANNER_OUTPUT_WIRE_VERSION, "p": {}, "a": None}
    with pytest.raises(SemanticPlanWireError, match="missing fields"):
        planner_output_from_wire(envelope)

    duplicate = '{"v":1,"v":1,"p":{},"a":null}'
    with pytest.raises(SemanticPlanWireError, match="Duplicate JSON field"):
        planner_output_from_json(duplicate)


def test_planner_output_schema_embeds_plan_and_bounded_answer() -> None:
    schema = planner_output_json_schema()
    properties = schema["properties"]

    assert schema["title"] == "OrionPlannerOutputV1"
    assert set(schema["required"]) == {"v", "p", "a"}
    assert properties["v"]["enum"] == [PLANNER_OUTPUT_WIRE_VERSION]
    assert properties["p"]["additionalProperties"] is False
    assert "direct_answer" in properties["p"]["properties"]["r"]["enum"]
    assert properties["a"]["anyOf"][0] == {
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_PLANNER_FINAL_ANSWER_LENGTH,
    }
    assert json.dumps(schema)
