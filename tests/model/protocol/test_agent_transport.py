from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import pytest

from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    ContractError,
    DecisionKind,
    FinalClaim,
    FinalClaimKind,
    decision_to_json,
)
from src.model.protocol.agent_transport import (
    agent_decision_json_schema,
    parse_agent_decision_payload,
)
from src.pipeline.calculator_action_contract import (
    CALCULATOR_CAPABILITY_ID,
    calculator_arguments_schema,
)


def _selected_schema() -> dict[str, object]:
    return {
        "capability_id": "host.cpu",
        "target_ref": {"applicable": True, "allowed_refs": ["monitor"]},
        "source_ref": {"applicable": False},
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


def _assert_schema_accepts(schema: Mapping[str, object], value: object) -> None:
    """Validate the JSON-Schema subset emitted by this transport."""
    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        errors: list[AssertionError] = []
        for candidate in any_of:
            assert isinstance(candidate, Mapping)
            try:
                _assert_schema_accepts(candidate, value)
            except AssertionError as exc:
                errors.append(exc)
            else:
                return
        raise AssertionError(f"value matches no anyOf branch: {errors}")

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        for candidate in one_of:
            assert isinstance(candidate, Mapping)
            try:
                _assert_schema_accepts(candidate, value)
            except AssertionError:
                continue
            matches += 1
        assert matches == 1

    expected_type = schema.get("type")
    if expected_type == "object":
        assert isinstance(value, Mapping)
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        assert isinstance(properties, Mapping)
        assert isinstance(required, list)
        assert all(key in value for key in required)
        if schema.get("additionalProperties") is False:
            assert set(value).issubset(properties)
        for key, property_schema in properties.items():
            if key in value:
                assert isinstance(property_schema, Mapping)
                _assert_schema_accepts(property_schema, value[key])
    elif expected_type == "array":
        assert isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        max_items = schema.get("maxItems")
        if isinstance(max_items, int):
            assert len(value) <= max_items
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for item in value:
                _assert_schema_accepts(item_schema, item)
    elif expected_type == "string":
        assert isinstance(value, str)
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int):
            assert len(value) >= min_length
        if isinstance(max_length, int):
            assert len(value) <= max_length
    elif expected_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool)
    elif expected_type == "number":
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected_type == "boolean":
        assert isinstance(value, bool)
    elif expected_type == "null":
        assert value is None

    enum = schema.get("enum")
    if isinstance(enum, list):
        assert value in enum


def _calculator_selected_schema() -> dict[str, object]:
    return {
        "capability_id": CALCULATOR_CAPABILITY_ID,
        "target_ref": {"applicable": False},
        "source_ref": {"applicable": False},
        "arguments_schema": calculator_arguments_schema(),
    }


def _decision_fixture(kind: str) -> AgentDecision:
    if kind == "final":
        return AgentDecision(
            kind=DecisionKind.FINAL,
            goal="Answer directly.",
            answer="Done.",
            claims=(
                FinalClaim(
                    kind=FinalClaimKind.DETERMINISTIC_RESULT,
                    action_id=1,
                    capability_id="host.cpu",
                    result={"value": 1},
                ),
            ),
        )
    if kind == "discover":
        return AgentDecision(
            kind=DecisionKind.DISCOVER,
            goal="Discover a capability.",
            category="host",
        )
    if kind == "action":
        return AgentDecision(
            kind=DecisionKind.ACTION,
            goal="Run a capability.",
            action=AgentAction(capability_id="host.cpu", arguments={}),
        )
    if kind == "clarify":
        return AgentDecision(
            kind=DecisionKind.CLARIFY,
            goal="Clarify the request.",
            question="Which target?",
        )
    if kind == "refuse":
        return AgentDecision(
            kind=DecisionKind.REFUSE,
            goal="Refuse the request.",
            reason="Cannot comply.",
        )
    raise AssertionError(f"unsupported fixture kind: {kind}")


def test_schema_uses_readable_protocol_fields() -> None:
    schema = agent_decision_json_schema()

    assert schema["title"] == "OrionAgentDecisionV3"
    assert "properties" not in schema
    assert len(schema["oneOf"]) == 5
    for branch in schema["oneOf"]:
        properties = branch["properties"]
        assert properties["version"]["enum"] == [3]
        assert branch["required"] == [
            "version",
            "kind",
            next(
                key
                for key in ("answer", "category", "action", "question", "reason")
                if key in properties
            ),
        ]


def test_selected_calculator_schema_requires_operation_specific_operands() -> None:
    schema = agent_decision_json_schema(_calculator_selected_schema())
    action_branch = next(
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )
    action_schema = action_branch["properties"]["action"]
    assert "target_ref" not in action_schema["properties"]
    assert "source_ref" not in action_schema["properties"]

    valid = {
        "version": 3,
        "kind": "action",
        "action": {
            "capability_id": CALCULATOR_CAPABILITY_ID,
            "arguments": {"operation": "multiply", "left": 287, "right": 419},
        },
    }
    _assert_schema_accepts(schema, valid)

    for invalid_arguments in (
        {"operation": "multiply"},
        {"operation": "multiply", "left": None, "right": None},
    ):
        with pytest.raises(AssertionError):
            _assert_schema_accepts(
                schema,
                {
                    **valid,
                    "action": {
                        "capability_id": CALCULATOR_CAPABILITY_ID,
                        "arguments": invalid_arguments,
                    },
                },
            )


@pytest.mark.parametrize(
    "allowed_kinds",
    (
        ("final", "discover", "action", "clarify", "refuse"),
        ("final", "discover", "clarify", "refuse"),
        ("action",),
        ("discover", "action", "clarify", "refuse"),
    ),
)
def test_stage_filtered_schemas_accept_only_their_allowed_wire_decisions(
    allowed_kinds: tuple[str, ...],
) -> None:
    schema = agent_decision_json_schema(allowed_kinds=allowed_kinds)

    for kind in allowed_kinds:
        _assert_schema_accepts(schema, _decision_fixture(kind).to_wire())

    for kind in {"final", "discover", "action", "clarify", "refuse"} - set(
        allowed_kinds
    ):
        with pytest.raises(AssertionError):
            _assert_schema_accepts(schema, _decision_fixture(kind).to_wire())


def test_recovery_schema_omits_final_only_claims_when_final_is_excluded() -> None:
    schema = agent_decision_json_schema(
        allowed_kinds=("discover", "action", "clarify", "refuse"),
    )

    for branch in schema["oneOf"]:
        assert "claims" not in branch["properties"]


def test_stage_schema_can_constrain_discovery_groups_and_action_ids() -> None:
    schema = agent_decision_json_schema(
        allowed_kinds=("discover", "action", "clarify", "refuse"),
        allowed_discovery_groups=("grafana",),
        allowed_action_capability_ids=("grafana.metrics",),
    )
    discover_branch = next(
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["discover"]
    )
    action_branch = next(
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )

    assert discover_branch["properties"]["category"] == {
        "type": "string",
        "enum": ["grafana"],
    }
    assert action_branch["properties"]["action"]["properties"]["capability_id"] == {
        "type": "string",
        "enum": ["grafana.metrics"],
    }


def test_action_schema_exposes_semantic_refs_and_activity() -> None:
    schema = agent_decision_json_schema(_selected_schema())

    action_branch = next(
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )
    action = action_branch["properties"]["action"]

    assert action["required"] == ["capability_id", "arguments"]
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
    assert action["properties"]["target_ref"] == {
        "type": "string",
        "enum": ["monitor"],
    }
    assert "source_ref" not in action["properties"]
    assert "activity_text" in action["properties"]


def test_selected_action_only_schema_accepts_its_closed_wire_fixture() -> None:
    schema = agent_decision_json_schema(
        _selected_schema(),
        allowed_kinds=("action",),
    )
    decision = AgentDecision(
        kind=DecisionKind.ACTION,
        goal="Inspect CPU.",
        action=AgentAction(
            capability_id="host.cpu",
            target_ref="monitor",
            arguments={"window_seconds": 60},
        ),
    )

    _assert_schema_accepts(schema, decision.to_wire())
    with pytest.raises(AssertionError):
        _assert_schema_accepts(schema, _decision_fixture("final").to_wire())


def test_selected_action_schema_omits_non_applicable_refs() -> None:
    schema = agent_decision_json_schema(
        {
            "capability_id": "compute.deterministic",
            "target_ref": {"applicable": False},
            "source_ref": {"applicable": False},
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
        allowed_kinds=("action",),
    )
    action = schema["oneOf"][0]["properties"]["action"]

    assert "target_ref" not in action["properties"]
    assert "source_ref" not in action["properties"]
    _assert_schema_accepts(
        schema,
        {
            "version": 3,
            "kind": "action",
            "action": {
                "capability_id": "compute.deterministic",
                "arguments": {},
            },
        },
    )
    with pytest.raises(AssertionError):
        _assert_schema_accepts(
            schema,
            {
                "version": 3,
                "kind": "action",
                "action": {
                    "capability_id": "compute.deterministic",
                    "target_ref": "result",
                    "arguments": {},
                },
            },
        )


def test_selected_action_schema_enumerates_only_disclosed_target_refs() -> None:
    schema = agent_decision_json_schema(
        {
            "capability_id": "host.inspect",
            "target_ref": {
                "applicable": True,
                "allowed_refs": ["monitor", "server01"],
            },
            "source_ref": {"applicable": False},
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
        allowed_kinds=("action",),
    )
    action = schema["oneOf"][0]["properties"]["action"]

    assert action["properties"]["target_ref"] == {
        "type": "string",
        "enum": ["monitor", "server01"],
    }


def test_dict_provider_payload_parses_to_canonical_decision() -> None:
    payload = {
        "version": 3,
        "kind": "action",
        "action": {
            "capability_id": "host.cpu",
            "target_ref": "monitor",
            "source_ref": "linux",
            "arguments": {"window_seconds": 60},
            "activity_text": "Checking CPU",
        },
    }

    decision = parse_agent_decision_payload(payload)

    assert decision == AgentDecision(
        kind=DecisionKind.ACTION,
        action=AgentAction(
            capability_id="host.cpu",
            target_ref="monitor",
            source_ref="linux",
            arguments={"window_seconds": 60},
            activity_text="Checking CPU",
        ),
    )


def test_final_claim_transport_is_closed_and_stage_valid() -> None:
    final = AgentDecision(
        kind=DecisionKind.FINAL,
        goal="Report CPU.",
        answer="CPU is healthy.",
        claims=(
            FinalClaim(
                kind=FinalClaimKind.DETERMINISTIC_RESULT,
                action_id=1,
                capability_id="host.cpu",
                target_ref="monitor",
                result={"logical_cores": 4},
            ),
        ),
    )
    assert AgentDecision.from_wire(final.to_wire()) == final

    invalid = final.to_wire()
    invalid["kind"] = "action"
    invalid["action"] = {
        "capability_id": "host.cpu",
        "target_ref": "monitor",
        "arguments": {},
    }
    with pytest.raises(ContractError, match="fields do not match"):
        AgentDecision.from_wire(invalid)


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
    action_branch = next(
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )
    action = action_branch["properties"]["action"]
    properties = action["properties"]

    assert properties["capability_id"]["maxLength"] == MAX_CAPABILITY_ID_CHARS
    assert properties["target_ref"]["maxLength"] == MAX_REFERENCE_CHARS
    assert properties["source_ref"]["maxLength"] == MAX_REFERENCE_CHARS
