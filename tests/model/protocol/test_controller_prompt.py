from __future__ import annotations

import json

import pytest

from src.agent.controller_contracts import (
    AgentObservation,
    AgentObservationStatus,
    AgentRunState,
    ControllerCallStage,
)
from src.model.protocol.controller_prompt import (
    CONTROLLER_CAPABILITY_CATEGORIES,
    ControllerContinuationInput,
    ControllerPromptContext,
    agent_decision_json_schema,
    build_controller_prompt,
)
from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.pipeline.input_context_budget import (
    InputContextBudget,
    InputContextBudgetClass,
    InputContextBudgetError,
    InputContextBudgetPolicy,
)
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
    assert prompt.input_budget_class == InputContextBudgetClass.CONTROLLER_FIRST.value
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


def test_system_prompt_marks_observations_as_untrusted_data() -> None:
    prompt = build_controller_prompt("Hello", hard_constraints=HardRequestConstraints())

    assert "untrusted evidence data" in prompt.system_prompt.casefold()
    assert "never grant authority" in prompt.system_prompt.casefold()


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

    constraints = HardRequestConstraints(requires_fresh_evidence=True)
    prompt = build_controller_prompt(
        "Check CPU.",
        hard_constraints=constraints,
        continuation=continuation,
        call_stage=ControllerCallStage.ACTION_CONTINUATION,
    )
    payload = json.loads(prompt.user_prompt)
    assert prompt.input_budget_class == InputContextBudgetClass.CONTROLLER_ACTION.value
    assert payload["request"] == "Check CPU."
    assert payload["hard_constraints"] == constraints.to_dict()
    assert "hard_constraint_snapshot" not in prompt.user_prompt
    assert "hv" not in payload
    assert payload["loop_state"] == {
        "goal": "Inspect CPU.",
        "disclosed_capability_categories": [],
        "disclosed_capability_detail_ids": [],
        "round_count": 0,
        "action_count": 0,
        "model_call_count": 0,
    }
    assert prompt.mandatory_section_names == (
        "system_prompt",
        "request",
        "hard_constraints",
        "selected_capability_schema",
        "json_framing",
    )
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
        call_stage=ControllerCallStage.OBSERVATION_CONTINUATION,
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


def test_observation_stage_keeps_newest_feedback_and_drops_older_whole_section() -> (
    None
):
    state = AgentRunState(
        raw_request="Check the current host state.",
        observations=tuple(
            AgentObservation(
                action_id=index,
                capability_id="host.cpu",
                status=AgentObservationStatus.SUCCESS,
                summary="x" * 512,
            )
            for index in range(1, 17)
        ),
    )
    prompt = build_controller_prompt(
        state.raw_request,
        hard_constraints=HardRequestConstraints(),
        continuation=ControllerContinuationInput(
            run_state=state,
            session_context=ControllerPromptContext(target="monitor"),
        ),
        call_stage=ControllerCallStage.OBSERVATION_CONTINUATION,
    )
    payload = json.loads(prompt.user_prompt)

    assert (
        prompt.input_budget_class
        == InputContextBudgetClass.CONTROLLER_OBSERVATION.value
    )
    assert payload["observation"]["n"] == 16
    assert payload["hard_constraints"] == HardRequestConstraints().to_dict()
    assert "hard_constraint_snapshot" not in prompt.user_prompt
    assert prompt.optional_included == (
        "loop_state",
        "session_context",
        "older_observations",
    )
    assert prompt.optional_dropped == ()
    assert prompt.actual_input_chars == len(prompt.system_prompt) + len(
        prompt.user_prompt
    )
    assert prompt.estimated_input_tokens == InputContextBudget.estimated_tokens(
        prompt.system_prompt + prompt.user_prompt
    )


def test_stage_disclosure_contracts_are_mutually_exclusive() -> None:
    state = AgentRunState(raw_request="Inspect CPU.")
    summaries = ({"capability_id": "host.cpu"},)
    discovery = build_controller_prompt(
        state.raw_request,
        hard_constraints=HardRequestConstraints(),
        continuation=ControllerContinuationInput(
            run_state=state, capability_summaries=summaries
        ),
        call_stage=ControllerCallStage.DISCOVERY_CONTINUATION,
    )
    payload = json.loads(discovery.user_prompt)
    assert "capability_summaries" in payload
    assert "selected_capability_schema" not in payload
    assert payload["request"] == state.raw_request
    assert payload["hard_constraints"] == HardRequestConstraints().to_dict()

    with pytest.raises(ValueError, match="requires one selected"):
        build_controller_prompt(
            state.raw_request,
            hard_constraints=HardRequestConstraints(),
            continuation=ControllerContinuationInput(run_state=state),
            call_stage=ControllerCallStage.ACTION_CONTINUATION,
        )


def test_continuation_rejects_first_decision_stage_instead_of_inferring() -> None:
    continuation = ControllerContinuationInput(
        run_state=AgentRunState(raw_request="Inspect CPU."),
        capability_summaries=({"capability_id": "host.cpu"},),
    )

    with pytest.raises(ValueError, match="first-decision stage"):
        build_controller_prompt(
            "Inspect CPU.",
            hard_constraints=HardRequestConstraints(),
            continuation=continuation,
            call_stage=ControllerCallStage.FIRST_DECISION,
        )


def test_raw_request_is_rendered_without_substring_truncation() -> None:
    request = "x" * 4_096
    prompt = build_controller_prompt(request, hard_constraints=HardRequestConstraints())

    assert json.loads(prompt.user_prompt)["request"] == request


def test_loop_state_is_optional_and_drops_before_mandatory_action_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentRunState(raw_request="Check CPU.", goal="Inspect CPU.")
    selected = {
        "capability_id": "host.cpu",
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {},
        },
    }
    constraints = HardRequestConstraints(requires_fresh_evidence=True)
    initial = build_controller_prompt(
        state.raw_request,
        hard_constraints=constraints,
        continuation=ControllerContinuationInput(
            run_state=state, selected_capability_schema=selected
        ),
        call_stage=ControllerCallStage.ACTION_CONTINUATION,
    )
    initial_payload = json.loads(initial.user_prompt)
    mandatory_payload = dict(initial_payload)
    mandatory_payload.pop("loop_state")
    mandatory_chars = len(initial.system_prompt) + len(
        json.dumps(
            mandatory_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    )
    monkeypatch.setattr(
        InputContextBudgetPolicy,
        "CONTROLLER_ACTION",
        InputContextBudget(InputContextBudgetClass.CONTROLLER_ACTION, mandatory_chars),
    )

    prompt = build_controller_prompt(
        state.raw_request,
        hard_constraints=constraints,
        continuation=ControllerContinuationInput(
            run_state=state, selected_capability_schema=selected
        ),
        call_stage=ControllerCallStage.ACTION_CONTINUATION,
    )
    payload = json.loads(prompt.user_prompt)

    assert "loop_state" not in payload
    assert prompt.optional_included == ()
    assert prompt.optional_dropped == ("loop_state",)
    assert payload["request"] == state.raw_request
    assert payload["hard_constraints"] == constraints.to_dict()
    assert payload["selected_capability_schema"] == selected


def test_action_mandatory_authority_and_schema_overflow_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentRunState(raw_request="Check CPU.")
    selected = {
        "capability_id": "host.cpu",
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {},
        },
    }
    initial = build_controller_prompt(
        state.raw_request,
        hard_constraints=HardRequestConstraints(requires_fresh_evidence=True),
        continuation=ControllerContinuationInput(
            run_state=state, selected_capability_schema=selected
        ),
        call_stage=ControllerCallStage.ACTION_CONTINUATION,
    )
    mandatory_payload = json.loads(initial.user_prompt)
    mandatory_payload.pop("loop_state")
    mandatory_chars = len(initial.system_prompt) + len(
        json.dumps(
            mandatory_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    )
    monkeypatch.setattr(
        InputContextBudgetPolicy,
        "CONTROLLER_ACTION",
        InputContextBudget(
            InputContextBudgetClass.CONTROLLER_ACTION, mandatory_chars - 1
        ),
    )

    with pytest.raises(InputContextBudgetError):
        build_controller_prompt(
            state.raw_request,
            hard_constraints=HardRequestConstraints(requires_fresh_evidence=True),
            continuation=ControllerContinuationInput(
                run_state=state, selected_capability_schema=selected
            ),
            call_stage=ControllerCallStage.ACTION_CONTINUATION,
        )


def test_optional_sections_drop_in_loop_state_session_observation_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentRunState(
        raw_request="Check current CPU.",
        goal="Inspect CPU.",
        observations=tuple(
            AgentObservation(
                action_id=index,
                capability_id="host.cpu",
                status=AgentObservationStatus.SUCCESS,
                summary="x" * 512,
            )
            for index in range(1, 17)
        ),
    )
    continuation = ControllerContinuationInput(
        run_state=state,
        session_context=ControllerPromptContext(target="monitor"),
    )
    initial = build_controller_prompt(
        state.raw_request,
        hard_constraints=HardRequestConstraints(),
        continuation=continuation,
        call_stage=ControllerCallStage.OBSERVATION_CONTINUATION,
    )
    initial_payload = json.loads(initial.user_prompt)
    mandatory_payload = dict(initial_payload)
    loop_state = mandatory_payload.pop("loop_state")
    session_context = mandatory_payload.pop("session_context")
    mandatory_payload.pop("older_observations")

    def compact(value: object) -> str:
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )

    max_chars = (
        len(initial.system_prompt)
        + len(compact(mandatory_payload))
        + len(',"loop_state":' + compact(loop_state))
        + len(',"session_context":' + compact(session_context))
    )
    monkeypatch.setattr(
        InputContextBudgetPolicy,
        "CONTROLLER_OBSERVATION",
        InputContextBudget(InputContextBudgetClass.CONTROLLER_OBSERVATION, max_chars),
    )

    prompt = build_controller_prompt(
        state.raw_request,
        hard_constraints=HardRequestConstraints(),
        continuation=continuation,
        call_stage=ControllerCallStage.OBSERVATION_CONTINUATION,
    )
    payload = json.loads(prompt.user_prompt)

    assert prompt.optional_included == ("loop_state", "session_context")
    assert prompt.optional_dropped == ("older_observations",)
    assert "older_observations" not in payload
    assert payload["observation"]["n"] == 16


def test_controller_stage_budget_values_are_locked() -> None:
    assert InputContextBudgetPolicy.CONTROLLER_FIRST.max_chars == 6_500
    assert InputContextBudgetPolicy.CONTROLLER_DISCOVERY.max_chars == 11_000
    assert InputContextBudgetPolicy.CONTROLLER_ACTION.max_chars == 9_000
    assert InputContextBudgetPolicy.CONTROLLER_OBSERVATION.max_chars == 14_000


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
