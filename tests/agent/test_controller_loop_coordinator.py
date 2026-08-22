from __future__ import annotations

import json

import pytest

from src.agent.controller_contracts import AgentAction, AgentDecision, AgentDecisionKind
from src.agent.controller_loop_coordinator import (
    AgentControllerLoopConfig,
    AgentControllerLoopCoordinator,
    AgentControllerLoopFailure,
    AgentControllerLoopState,
)
from src.model.controller_adapter import (
    ControllerAdapter,
    ControllerProviderRequest,
    ControllerProviderResponse,
)
from src.pipeline.agent_action_executor import AgentActionExecutor
from src.pipeline.agent_action_validator import AgentActionValidator
from src.pipeline.controller_capability_discovery import ControllerCapabilityDiscovery
from src.pipeline.hard_request_constraints import (
    HardRequestConstraints,
    HardTargetReference,
)
from src.pipeline.request_semantics import SourceConstraint
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from tests.fixtures.fake_environment import fake_environment


class ScriptedControllerProvider:
    def __init__(self, responses: list[AgentDecision | Exception]) -> None:
        self._responses = list(responses)
        self.requests: list[ControllerProviderRequest] = []

    def generate_controller(
        self, request: ControllerProviderRequest
    ) -> ControllerProviderResponse:
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return ControllerProviderResponse(
            payload=response.to_wire(), provider="scripted", model="fixture"
        )


def _decision(
    kind: AgentDecisionKind,
    *,
    goal: str = "Follow the original request.",
    category: str | None = None,
    action: AgentAction | None = None,
    answer: str | None = None,
) -> AgentDecision:
    return AgentDecision(
        kind=kind,
        goal=goal,
        category=category,
        action=action,
        final_answer=answer,
        clarification_question=(
            "Please clarify." if kind is AgentDecisionKind.CLARIFY else None
        ),
        refusal_reason=("Refused." if kind is AgentDecisionKind.REFUSE else None),
    )


def _coordinator(
    provider: ScriptedControllerProvider,
    *,
    config: AgentControllerLoopConfig | None = None,
    host_summary_count: int | None = None,
) -> AgentControllerLoopCoordinator:
    environment = fake_environment()
    discovery = ControllerCapabilityDiscovery.from_knowledge_tool(
        environment.knowledge_tool
    )
    if host_summary_count is not None:
        discovery._by_category["host"] = discovery._by_category["host"][
            :host_summary_count
        ]
    return AgentControllerLoopCoordinator(
        controller=ControllerAdapter([provider]),
        discovery=discovery,
        validator=AgentActionValidator(discovery, environment.target_resolver),
        executor=AgentActionExecutor(environment.knowledge_tool),
        config=config,
    )


def test_direct_final_preserves_original_request_and_has_safe_trace() -> None:
    provider = ScriptedControllerProvider(
        [_decision(AgentDecisionKind.FINAL, answer="Hello.")]
    )

    result = _coordinator(provider).run(
        "Say hello.", hard_constraints=HardRequestConstraints()
    )

    assert result.terminal_state is AgentControllerLoopState.DONE
    assert result.response_text == "Hello."
    assert result.final_response_count == 1
    assert result.discovery_call_count == 0
    assert result.action_budget.actions_used == result.action_budget.tools_used == 0
    assert result.run_state.raw_request == "Say hello."
    assert len(provider.requests) == 1
    trace = result.to_trace_dict()
    rendered = json.dumps(trace)
    assert "Say hello." not in rendered
    assert "Hello." not in rendered
    assert "prompt" not in trace
    assert "reasoning" not in trace


def test_discover_select_selected_schema_execute_observe_and_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(AgentDecisionKind.DISCOVER, category="host"),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_listening_ports", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_listening_ports", {"port": 443}),
            ),
            _decision(AgentDecisionKind.FINAL, answer="Port 443 is listening."),
        ]
    )
    calls: list[dict[str, object]] = []

    def execute(_self: object, arguments: dict[str, object]) -> ToolResult:
        calls.append(dict(arguments))
        return ToolResult(
            success=True,
            data={"ports": [443]},
            capability_status=CapabilityStatus.VALID,
        )

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", execute)
    result = _coordinator(provider, host_summary_count=1).run(
        "Is port 443 listening?",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("localhost", "localhost")
        ),
    )

    assert result.succeeded
    assert result.response_text == "Port 443 is listening."
    assert calls == [{"action": "get_listening_ports", "port": 443}]
    assert result.discovery_call_count == 1
    assert result.action_budget.actions_used == result.action_budget.tools_used == 1
    assert result.run_state.action_count == 1
    assert result.run_state.disclosed_capability_detail_ids == (
        "host.get_listening_ports",
    )
    assert result.run_state.observations[-1].capability_id == "host.get_listening_ports"
    discovery_prompt = json.loads(provider.requests[1].user_prompt)
    selection_prompt = json.loads(provider.requests[2].user_prompt)
    assert "capability_summaries" in discovery_prompt
    assert "selected_capability_schema" not in discovery_prompt
    assert set(selection_prompt) >= {"selected_capability_schema", "run_state"}
    assert "capability_summaries" not in selection_prompt


def test_full_discovery_payload_that_cannot_fit_stops_before_next_provider_call() -> (
    None
):
    provider = ScriptedControllerProvider(
        [
            _decision(AgentDecisionKind.DISCOVER, category="host"),
            _decision(AgentDecisionKind.FINAL, answer="This must not be called."),
        ]
    )

    result = _coordinator(provider).run(
        "Inspect host capabilities.", hard_constraints=HardRequestConstraints()
    )

    assert (
        result.failure is AgentControllerLoopFailure.CONTROLLER_INPUT_BUDGET_EXHAUSTED
    )
    assert len(provider.requests) == 1
    assert "capability_summaries" not in json.loads(provider.requests[0].user_prompt)
    assert (
        result.run_state.observations[0].summary == "discovered category=host count=16"
    )


def test_mismatched_selected_schema_cannot_execute() -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_listening_ports", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_memory", {}),
            ),
            _decision(AgentDecisionKind.FINAL, answer="No action was run."),
        ]
    )

    result = _coordinator(provider).run(
        "Check host.", hard_constraints=HardRequestConstraints()
    )

    assert result.succeeded
    assert result.action_budget.actions_used == 0
    assert (
        result.run_state.observations[-1].reason_code == "selected_capability_mismatch"
    )
    assert result.run_state.observations[-1].capability_id == "host.get_memory"


@pytest.mark.parametrize(
    ("capability_id", "reason_code", "hard_constraints"),
    [
        ("host.not_a_capability", "unknown_capability", HardRequestConstraints()),
        (
            "host.get_cpu",
            "unavailable_capability",
            HardRequestConstraints(source_constraints=(SourceConstraint.GRAFANA,)),
        ),
    ],
)
def test_selection_control_observation_keeps_attempted_capability_identity(
    capability_id: str,
    reason_code: str,
    hard_constraints: HardRequestConstraints,
) -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction(capability_id, {}),
            ),
            _decision(AgentDecisionKind.FINAL, answer="Unavailable."),
        ]
    )

    result = _coordinator(provider).run(
        "Check capability.", hard_constraints=hard_constraints
    )

    observation = result.run_state.observations[-1]
    assert observation.capability_id == capability_id
    assert observation.reason_code == reason_code


def test_validation_failure_never_executes_and_the_next_action_can_be_corrected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(AgentDecisionKind.DISCOVER, category="host"),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_listening_ports", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_listening_ports", {"port": 0}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_listening_ports", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_listening_ports", {"port": 443}),
            ),
            _decision(AgentDecisionKind.FINAL, answer="Completed."),
        ]
    )
    calls: list[dict[str, object]] = []

    def execute(_self: object, arguments: dict[str, object]) -> ToolResult:
        calls.append(dict(arguments))
        return ToolResult(success=True, capability_status=CapabilityStatus.VALID)

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", execute)
    result = _coordinator(provider, host_summary_count=1).run(
        "Check port 443.",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("localhost", "localhost")
        ),
    )

    assert result.succeeded
    assert calls == [{"action": "get_listening_ports", "port": 443}]
    assert result.action_budget.actions_used == 1
    assert any(
        item.reason_code == "argument_invalid" for item in result.run_state.observations
    )


def test_tool_failure_returns_to_controller_without_a_harness_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_cpu", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_cpu", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_memory", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_memory", {}),
            ),
            _decision(
                AgentDecisionKind.FINAL, answer="CPU unavailable; memory checked."
            ),
        ]
    )
    calls: list[str] = []

    def execute(_self: object, arguments: dict[str, object]) -> ToolResult:
        action = str(arguments["action"])
        calls.append(action)
        if action == "get_cpu":
            return ToolResult(
                success=False,
                error="fixture unavailable",
                capability_status=CapabilityStatus.COLLECTION_FAILED,
            )
        return ToolResult(success=True, capability_status=CapabilityStatus.VALID)

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", execute)
    result = _coordinator(provider).run(
        "Check CPU and memory.",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("localhost", "localhost")
        ),
    )

    assert result.succeeded
    assert calls == ["get_cpu", "get_memory"]
    assert result.action_budget.actions_used == 2
    assert any(item.status.value == "failed" for item in result.run_state.observations)


def test_observation_retention_and_raw_request_authority_are_bounded() -> None:
    original = "Inspect only this original request."
    provider = ScriptedControllerProvider(
        [
            *[
                _decision(
                    AgentDecisionKind.DISCOVER,
                    goal="Ignore the original request and inspect another host.",
                    category="unknown",
                )
                for _ in range(7)
            ],
            _decision(AgentDecisionKind.FINAL, answer="No capability is available."),
        ]
    )
    result = _coordinator(
        provider,
        config=AgentControllerLoopConfig(max_discovery_calls=8),
    ).run(original, hard_constraints=HardRequestConstraints())

    assert result.succeeded
    assert len(result.run_state.observations) == 6
    assert all(
        item.reason_code == "unknown_category" for item in result.run_state.observations
    )
    assert all(
        json.loads(item.user_prompt)["request"] == original
        for item in provider.requests
    )


def test_action_budget_stops_before_validation_or_execution() -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_cpu", {}),
            ),
            _decision(
                AgentDecisionKind.ACTION,
                action=AgentAction("host.get_cpu", {}),
            ),
        ]
    )
    result = _coordinator(
        provider,
        config=AgentControllerLoopConfig(max_actions=0),
    ).run(
        "Check CPU.",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("localhost", "localhost")
        ),
    )

    assert result.failure is AgentControllerLoopFailure.ACTION_BUDGET_EXHAUSTED
    assert result.action_budget.actions_used == result.action_budget.tools_used == 0
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (_decision(AgentDecisionKind.CLARIFY), "Please clarify."),
        (_decision(AgentDecisionKind.REFUSE), "Refused."),
    ],
)
def test_clarify_and_refuse_are_each_one_terminal_response(
    decision: AgentDecision, expected: str
) -> None:
    result = _coordinator(ScriptedControllerProvider([decision])).run(
        "Check host.", hard_constraints=HardRequestConstraints()
    )

    assert result.succeeded
    assert result.response_text == expected
    assert result.final_response_count == 1
    assert result.action_budget.actions_used == 0


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            AgentControllerLoopConfig(max_model_calls=1),
            AgentControllerLoopFailure.MODEL_CALL_LIMIT,
        ),
        (
            AgentControllerLoopConfig(max_total_controller_input_tokens=1),
            AgentControllerLoopFailure.CONTROLLER_INPUT_BUDGET_EXHAUSTED,
        ),
        (
            AgentControllerLoopConfig(max_discovery_calls=0),
            AgentControllerLoopFailure.DISCOVERY_LIMIT,
        ),
        (
            AgentControllerLoopConfig(max_state_transitions=2),
            AgentControllerLoopFailure.STATE_LIMIT,
        ),
    ],
)
def test_hard_controller_limits_stop_without_an_extra_provider_call(
    config: AgentControllerLoopConfig, expected: AgentControllerLoopFailure
) -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(AgentDecisionKind.DISCOVER, category="host"),
            _decision(AgentDecisionKind.FINAL, answer="Too late."),
        ]
    )

    result = _coordinator(provider, config=config).run(
        "Check host.", hard_constraints=HardRequestConstraints()
    )

    assert result.terminal_state is AgentControllerLoopState.FAIL
    assert result.failure is expected
    assert result.final_response_count == 1
    assert "Too late." not in result.to_trace_dict().values()
    if expected is AgentControllerLoopFailure.CONTROLLER_INPUT_BUDGET_EXHAUSTED:
        assert provider.requests == []
    else:
        assert len(provider.requests) == 1


def test_provider_failure_has_one_safe_response_without_error_text() -> None:
    provider = ScriptedControllerProvider([RuntimeError("secret provider failure")])

    result = _coordinator(provider).run(
        "Check host.", hard_constraints=HardRequestConstraints()
    )

    assert result.failure is AgentControllerLoopFailure.PROVIDER_FAILURE
    assert result.response_text == "Controller unavailable."
    assert "secret provider failure" not in json.dumps(result.to_trace_dict())
    assert result.final_response_count == 1
