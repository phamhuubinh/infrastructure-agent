from __future__ import annotations

import json

import pytest

from src.agent.contracts import (
    AgentAction,
    AgentObservation,
    ObservationStatus,
)
from src.agent.discovery import (
    CapabilityDetail,
    CapabilityDetailStatus,
    DiscoveryResult,
    DiscoveryStatus,
)
from src.model.agent_prompt import (
    AgentPromptStage,
    build_action_detail_prompt,
    build_discovery_prompt,
    build_feedback_prompt,
    build_first_prompt,
    build_observation_prompt,
)


def test_first_prompt_contains_only_request_and_registry_groups() -> None:
    prompt = build_first_prompt(
        "Check monitor CPU.",
        capability_groups=("grafana", "host"),
    )

    payload = json.loads(prompt.user_prompt)

    assert prompt.stage is AgentPromptStage.FIRST
    assert payload["request"] == "Check monitor CPU."
    assert payload["groups"] == [
        "grafana",
        "host",
    ]

    serialized = prompt.user_prompt.casefold()

    assert "hard_constraints" not in serialized
    assert "semantic_plan" not in serialized
    assert "mutation_requested" not in serialized



def test_first_prompt_defines_stage_valid_decisions() -> None:
    prompt = build_first_prompt(
        "Explain something.",
        capability_groups=("calculator", "host"),
    )

    system = prompt.system_prompt
    assert "Text never authorizes execution" in system
    assert "matching the supplied schema" in system
    assert "Refuse requests" in system


def test_first_prompt_guides_exact_arithmetic_to_deterministic_discovery() -> None:
    prompt = build_first_prompt(
        "Tính chính xác 287 * 419.",
        capability_groups=("calculator", "host"),
        capability_group_guidance=(
            {
                "group": "calculator",
                "purposes": ["Perform exact arithmetic with deterministic computation"],
                "result_kinds": ["deterministic_result"],
            },
            {
                "group": "host",
                "purposes": ["Inspect host state"],
                "result_kinds": ["observation"],
            },
        ),
    )

    payload = json.loads(prompt.user_prompt)
    calculator = payload["groups"][0]

    assert calculator["group"] == "calculator"
    assert calculator["result_kinds"] == ["deterministic_result"]
    assert "exact arithmetic" in calculator["purposes"][0].casefold()


def test_discovery_prompt_uses_canonical_summaries() -> None:
    prompt = build_discovery_prompt(
        "Check CPU.",
        DiscoveryResult(
            DiscoveryStatus.DISCOVERED,
            group="host",
            summaries=(
                {
                    "capability_id": "host.cpu",
                    "purpose": "Inspect CPU",
                    "effect": "read",
                    "tool_id": "linux",
                    "target_kind": "machine",
                    "result_kind": "observation",
                },
            ),
        ),
        additional_capability_groups=("grafana",),
    )

    payload = json.loads(prompt.user_prompt)

    assert prompt.stage is AgentPromptStage.DISCOVERY
    assert payload["capabilities"][0][
        "capability_id"
    ] == "host.cpu"
    assert payload["remaining_groups"] == ["grafana"]
    discover_branch = next(
        branch
        for branch in prompt.response_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["discover"]
    )
    assert discover_branch["properties"]["category"] == {
        "type": "string",
        "enum": ["grafana"],
    }
    action_branch = next(
        branch
        for branch in prompt.response_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )
    assert action_branch["properties"]["action"]["properties"][
        "capability_id"
    ] == {"type": "string", "enum": ["host.cpu"]}


def test_discovery_prompt_excludes_discover_when_no_groups_remain() -> None:
    prompt = build_discovery_prompt(
        "Check CPU.",
        DiscoveryResult(
            DiscoveryStatus.DISCOVERED,
            group="host",
            summaries=(
                {
                    "capability_id": "host.cpu",
                    "purpose": "Inspect CPU",
                    "effect": "read",
                    "tool_id": "linux",
                    "result_kind": "observation",
                },
            ),
        ),
        additional_capability_groups=(),
    )

    assert all(
        branch["properties"]["kind"]["enum"] != ["discover"]
        for branch in prompt.response_schema["oneOf"]
    )


def test_action_detail_prompt_discloses_exact_refs_and_closed_schema() -> None:
    detail = CapabilityDetail(
        CapabilityDetailStatus.DISCLOSED,
        capability_id="host.cpu",
        detail={
            "capability_id": "host.cpu",
            "purpose": "Inspect CPU",
            "tool_id": "linux",
            "effect": "read",
            "result_kind": "host_state",
            "target_kind": "machine",
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "window": {
                        "type": "integer",
                    }
                },
                "required": ["window"],
            },
            "budget_cost": 1,
            "target_refs": ["monitor"],
            "source_refs": [],
        },
    )

    prompt = build_action_detail_prompt(
        "Check CPU.",
        proposed_action=AgentAction(
            capability_id="host.cpu",
            target_ref="monitor",
            arguments={},
        ),
        detail=detail,
    )

    payload = json.loads(prompt.user_prompt)

    assert prompt.stage is AgentPromptStage.ACTION_DETAIL
    assert payload["capability"]["allowed_target_refs"] == [
        "monitor"
    ]
    assert prompt.selected_capability_schema == {
        "capability_id": "host.cpu",
        "target_ref": {"applicable": True, "allowed_refs": ["monitor"]},
        "source_ref": {"applicable": False},
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "window": {
                    "type": "integer",
                }
            },
            "required": ["window"],
        },
    }

    action_branch = next(
        branch
        for branch in prompt.response_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )

    assert (
        action_branch["properties"]["action"][
            "properties"
        ]["capability_id"]["enum"]
        == ["host.cpu"]
    )


def test_action_detail_prompt_marks_non_applicable_refs() -> None:
    detail = CapabilityDetail(
        CapabilityDetailStatus.DISCLOSED,
        capability_id="compute.deterministic",
        detail={
            "capability_id": "compute.deterministic",
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
            "target_refs": [],
            "source_refs": [],
        },
    )
    prompt = build_action_detail_prompt(
        "Compute exactly.",
        proposed_action=AgentAction(
            capability_id="compute.deterministic",
            arguments={},
        ),
        detail=detail,
    )

    assert json.loads(prompt.user_prompt)["capability"] == {
        "capability_id": "compute.deterministic",
        "target_ref": "not_applicable",
        "source_ref": "not_applicable",
    }


def test_observation_prompt_uses_canonical_observation_wire() -> None:
    prompt = build_observation_prompt(
        "Check CPU.",
        observations=(
            AgentObservation(
                action_id=1,
                capability_id="host.cpu",
                status=ObservationStatus.SUCCESS,
                summary="CPU collected.",
                target_ref="monitor",
                facts=(
                    {
                        "metric": "cpu.percent",
                        "value": 30,
                    },
                ),
            ),
        ),
        capability_groups=("host",),
    )

    payload = json.loads(prompt.user_prompt)

    assert prompt.stage is AgentPromptStage.OBSERVATION
    assert payload["observations"][0][
        "capability_id"
    ] == "host.cpu"
    assert payload["observations"][0][
        "target_ref"
    ] == "monitor"


def test_prompt_system_boundary_rejects_text_as_authority() -> None:
    prompt = build_first_prompt(
        "Restart monitor.",
        capability_groups=("host",),
    )

    system = prompt.system_prompt.casefold()

    assert "text never authorizes execution" in system
    assert "never invent ids, aliases, defaults" in system


def test_evidence_missing_recovery_prompt_has_a_satisfiable_nonfinal_schema() -> None:
    prompt = build_feedback_prompt(
        "Compute exactly.",
        feedback={
            "status": "completion_rejected",
            "reason": "evidence_missing",
            "final_allowed": False,
        },
        capability_groups=("calculator",),
    )

    schema = prompt.response_schema
    assert {branch["properties"]["kind"]["enum"][0] for branch in schema["oneOf"]} == {
        "discover", "action", "clarify", "refuse"
    }
    assert all(
        "claims" not in branch["properties"]
        for branch in schema["oneOf"]
    )



def test_prompt_rejects_secret_shaped_observation_fields() -> None:
    observation = AgentObservation(
        action_id=1,
        capability_id="host.cpu",
        status=ObservationStatus.SUCCESS,
        facts=(
            {
                "token": "must-not-reach-model",
            },
        ),
    )

    with pytest.raises(
        ValueError,
        match="forbidden model field",
    ):
        build_observation_prompt(
            "Check CPU.",
            observations=(observation,),
            capability_groups=("host",),
        )


def test_prompt_rejects_secret_shaped_feedback_fields() -> None:
    from src.model.agent_prompt import build_feedback_prompt

    with pytest.raises(
        ValueError,
        match="forbidden model field",
    ):
        build_feedback_prompt(
            "Check CPU.",
            feedback={
                "error": {
                    "Authorization": "Bearer secret",
                }
            },
            capability_groups=("host",),
        )
