from __future__ import annotations

import json

import pytest

from src.agent.controller_contracts import (
    AgentObservation,
    AgentObservationStatus,
    AgentRunState,
)
from src.model.protocol.controller_prompt import (
    CONTROLLER_CAPABILITY_CATEGORIES,
    ControllerContinuationInput,
    ControllerPromptContext,
    agent_decision_json_schema,
    build_controller_prompt,
)
from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.pipeline.input_context_budget import InputContextBudgetClass
from src.pipeline.request_semantics import SourceConstraint


def test_first_turn_has_only_allowlisted_input_and_no_sensitive_detail() -> None:
    prompt = build_controller_prompt(
        "Check CPU on monitor.",
        hard_constraints=HardRequestConstraints(),
        context=ControllerPromptContext(
            target="monitor",
            concept="cpu",
            sources=(SourceConstraint.GRAFANA,),
        ),
    )
    payload = json.loads(prompt.user_prompt)
    combined = prompt.system_prompt + prompt.user_prompt

    assert set(payload) == {
        "request",
        "hard_constraints",
        "capability_categories",
        "session_context",
    }
    assert payload["capability_categories"] == list(CONTROLLER_CAPABILITY_CATEGORIES)
    assert payload["session_context"] == {
        "target": "monitor",
        "concept": "cpu",
        "sources": ["grafana"],
    }
    assert prompt.input_budget_class == InputContextBudgetClass.SIMPLE.value
    for forbidden in (
        "linux_tool",
        "capability_id",
        "api_key",
        "password",
        "evidence dump",
        "raw_payload",
    ):
        assert forbidden not in combined.casefold()


def test_system_prompt_requests_no_hidden_reasoning() -> None:
    prompt = build_controller_prompt("Hello", hard_constraints=HardRequestConstraints())

    assert "hidden reasoning" in prompt.system_prompt.casefold()
    assert "chain-of-thought" not in prompt.system_prompt.casefold()
    assert "explain your reasoning" not in prompt.system_prompt.casefold()


def test_context_and_continuation_data_are_bounded_before_provider_use() -> None:
    with pytest.raises(ValueError, match="byte limit"):
        build_controller_prompt(
            "Hello",
            hard_constraints=HardRequestConstraints(),
            context=ControllerPromptContext(
                target="x" * 256,
                concept="y" * 256,
                service="z" * 256,
                path="p" * 256,
            ),
        )

    state = AgentRunState(
        raw_request="Check CPU.",
        goal="Inspect CPU.",
        observations=(
            AgentObservation(
                action_id=1,
                capability_id="host.cpu",
                status=AgentObservationStatus.SUCCESS,
                summary="CPU usage is 80%.",
            ),
        ),
    )
    continuation = ControllerContinuationInput(
        run_state=state,
        selected_capability_schema={
            "capability_id": "host.cpu",
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["target_id"],
                "properties": {"target_id": {"type": "string"}},
            },
        },
        harness_feedback={"status": "approved"},
    )

    prompt = build_controller_prompt(
        "Check CPU.",
        hard_constraints=HardRequestConstraints(),
        continuation=continuation,
    )
    payload = json.loads(prompt.user_prompt)
    assert prompt.input_budget_class == InputContextBudgetClass.NORMAL.value
    assert payload["run_state"]["o"][0]["i"] == "host.cpu"
    assert payload["selected_capability_schema"] == {
        "capability_id": "host.cpu",
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["target_id"],
            "properties": {"target_id": {"type": "string"}},
        },
    }
    assert "capability_summaries" not in payload
    assert "session_context" not in payload

    with pytest.raises(ValueError, match="not both"):
        ControllerContinuationInput(
            run_state=state,
            capability_summaries=({"id": "host.cpu"},),
            selected_capability_schema={
                "capability_id": "host.cpu",
                "arguments_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [],
                    "properties": {},
                },
            },
        )


def test_continuation_reuses_the_same_allowlisted_evidence_free_session_context() -> (
    None
):
    continuation = ControllerContinuationInput(
        run_state=AgentRunState(raw_request="Còn RAM thì sao?"),
        session_context=ControllerPromptContext(
            target="monitor",
            sources=(SourceConstraint.GRAFANA,),
            excluded_sources=(SourceConstraint.INTERNET,),
        ),
    )

    prompt = build_controller_prompt(
        "Còn RAM thì sao?",
        hard_constraints=HardRequestConstraints(),
        continuation=continuation,
    )
    context = json.loads(prompt.user_prompt)["session_context"]

    assert context == {
        "target": "monitor",
        "sources": ["grafana"],
        "exclude": ["internet"],
    }
    assert len(json.dumps(context, ensure_ascii=False).encode("utf-8")) <= 1024
    assert not {
        "previous_evidence_receipts",
        "fact_ids",
        "last_evidence_status",
        "facts",
        "observations",
        "stdout",
        "stderr",
        "command",
    }.intersection(context)


def test_first_turn_action_arguments_are_closed_and_empty() -> None:
    schema = agent_decision_json_schema()
    action = schema["properties"]["a"]["anyOf"][0]
    arguments = action["properties"]["a"]

    assert arguments == {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }


def test_selected_capability_schema_allows_only_declared_typed_arguments() -> None:
    selected = {
        "capability_id": "host.cpu",
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["target_id", "window_minutes"],
            "properties": {
                "target_id": {"type": "string", "minLength": 1},
                "window_minutes": {"type": "integer", "minimum": 1},
            },
        },
    }
    schema = agent_decision_json_schema(selected)
    action = schema["properties"]["a"]["anyOf"][0]
    action_properties = action["properties"]
    arguments = action_properties["a"]

    assert action_properties["i"] == {"type": "string", "enum": ["host.cpu"]}
    assert arguments["additionalProperties"] is False
    assert set(arguments["properties"]) == {"target_id", "window_minutes"}
    assert "undeclared" not in arguments["properties"]
