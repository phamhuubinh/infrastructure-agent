from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from src.agent.controller_contracts import AgentAction, AgentDecision, AgentDecisionKind
from src.agent.controller_loop_coordinator import (
    AgentControllerLoopConfig,
    AgentControllerLoopCoordinator,
    AgentControllerLoopFailure,
    AgentControllerLoopState,
)
from src.agent.controller_session_context import ControllerSessionContext
from src.agent.conversation_store import ConversationStore
from src.agent.session_investigation_context import SessionInvestigationContext
from src.model.controller_adapter import (
    ControllerAdapter,
    ControllerProviderRequest,
    ControllerProviderResponse,
)
from src.pipeline.agent_action_executor import AgentActionExecutor
from src.pipeline.agent_action_validator import (
    AgentActionValidationReason,
    AgentActionValidationResult,
    AgentActionValidationStatus,
    AgentActionValidator,
)
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
    final_boundary: Callable[[str], str] | None = None,
    environment_flags: dict[str, object] | None = None,
) -> AgentControllerLoopCoordinator:
    environment = fake_environment(**(environment_flags or {}))
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
        final_boundary=final_boundary,
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


def test_rejected_final_returns_control_feedback_to_same_controller() -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(AgentDecisionKind.FINAL, answer="CPU is healthy."),
            _decision(
                AgentDecisionKind.FINAL,
                answer="The current value could not be verified from available evidence.",
            ),
        ]
    )
    final_boundary_calls: list[str] = []

    def final_boundary(answer: str) -> str:
        final_boundary_calls.append(answer)
        return answer

    result = _coordinator(provider, final_boundary=final_boundary).run(
        "Check current CPU.",
        hard_constraints=HardRequestConstraints(requires_fresh_evidence=True),
    )

    assert result.succeeded
    assert len(provider.requests) == 2
    assert final_boundary_calls == [result.response_text]
    assert result.completion_feedback_count == 1
    assert result.run_state.observations[-1].reason_code == (
        "goal_unresolved.current_evidence_missing"
    )


def test_completion_feedback_limit_stops_without_an_extra_provider_call() -> None:
    provider = ScriptedControllerProvider(
        [
            _decision(AgentDecisionKind.FINAL, answer="Current value is 1."),
            _decision(AgentDecisionKind.FINAL, answer="Current value is 1."),
        ]
    )

    result = _coordinator(
        provider,
        config=AgentControllerLoopConfig(max_completion_feedback=1),
    ).run(
        "Check current CPU.",
        hard_constraints=HardRequestConstraints(requires_fresh_evidence=True),
    )

    assert result.failure is AgentControllerLoopFailure.COMPLETION_FEEDBACK_LIMIT
    assert len(provider.requests) == 2
    assert result.completion_feedback_count == 1


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
            _decision(
                AgentDecisionKind.FINAL,
                answer="Port 443 could not be verified from available evidence.",
            ),
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
    assert (
        result.response_text
        == "Port 443 could not be verified from available evidence."
    )
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
            _decision(
                AgentDecisionKind.FINAL,
                answer="The result could not be verified from available evidence.",
            ),
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
            _decision(
                AgentDecisionKind.FINAL,
                answer="The result could not be verified from available evidence.",
            ),
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


def _session_store(
    tmp_path: object, session_id: str = "v2-session"
) -> ConversationStore:
    return ConversationStore(session_id, store_dir=str(tmp_path))


def _host_action_sequence(capability_id: str = "host.get_cpu") -> list[AgentDecision]:
    return [
        _decision(AgentDecisionKind.ACTION, action=AgentAction(capability_id, {})),
        _decision(AgentDecisionKind.ACTION, action=AgentAction(capability_id, {})),
        _decision(
            AgentDecisionKind.FINAL,
            answer="The current value could not be verified from available evidence.",
        ),
    ]


def test_session_target_is_persisted_after_valid_action_and_inherited_on_follow_up(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    first = _coordinator(
        ScriptedControllerProvider(_host_action_sequence()),
        environment_flags={"monitor": True},
    ).run(
        "Inspect CPU on monitor.",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("monitor", "monitor")
        ),
        session_store=store,
    )

    assert first.succeeded
    assert store.investigation_context.active_target == "monitor"

    provider = ScriptedControllerProvider(_host_action_sequence())
    follow_up = _coordinator(provider, environment_flags={"monitor": True}).run(
        "Còn RAM thì sao?",
        hard_constraints=HardRequestConstraints(),
        session_store=store,
    )

    assert follow_up.succeeded
    assert any(
        observation.target_id == "monitor"
        for observation in follow_up.run_state.observations
    )
    assert all(
        json.loads(request.user_prompt)["session_context"]["target"] == "monitor"
        for request in provider.requests
    )


def test_network_follow_up_uses_the_validated_session_target(tmp_path: object) -> None:
    store = _session_store(tmp_path)
    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )
    result = _coordinator(
        ScriptedControllerProvider(_host_action_sequence("host.get_network")),
        environment_flags={"monitor": True},
    ).run(
        "Còn network?",
        hard_constraints=HardRequestConstraints(),
        session_store=store,
    )

    assert result.succeeded
    assert any(
        observation.capability_id == "host.get_network"
        and observation.target_id == "monitor"
        for observation in result.run_state.observations
    )


def test_explicit_target_directive_updates_only_its_session_without_execution(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    provider = ScriptedControllerProvider([])

    result = _coordinator(provider, environment_flags={"monitor": True}).run(
        "Đừng dùng localhost nữa, chỉ dùng monitor cho các câu tiếp theo.",
        hard_constraints=HardRequestConstraints(),
        session_store=store,
    )

    assert result.succeeded
    assert store.investigation_context.active_target == "monitor"
    assert provider.requests == []
    assert result.action_budget.actions_used == result.action_budget.tools_used == 0


def test_unknown_explicit_target_never_reuses_or_replaces_stored_target(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )
    provider = ScriptedControllerProvider(
        [
            _decision(AgentDecisionKind.ACTION, action=AgentAction("host.get_cpu", {})),
            _decision(AgentDecisionKind.ACTION, action=AgentAction("host.get_cpu", {})),
            _decision(
                AgentDecisionKind.FINAL,
                answer="The current value could not be verified from available evidence.",
            ),
        ]
    )

    result = _coordinator(provider, environment_flags={"monitor": True}).run(
        "Inspect CPU on foo123.",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("foo123", None)
        ),
        session_store=store,
    )

    assert result.succeeded
    assert result.action_budget.actions_used == 0
    assert store.investigation_context.active_target == "monitor"
    assert store.investigation_context.pending_clarification_field == "target"


def test_explicit_localhost_replaces_inherited_monitor_after_validation(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )

    result = _coordinator(
        ScriptedControllerProvider(_host_action_sequence()),
        environment_flags={"monitor": True},
    ).run(
        "Inspect CPU on localhost.",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("localhost", "localhost")
        ),
        session_store=store,
    )

    assert result.succeeded
    assert any(
        observation.target_id == "localhost"
        for observation in result.run_state.observations
    )
    assert store.investigation_context.active_target == "localhost"


def test_explicit_source_policy_persists_and_is_reused_for_a_follow_up(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    first = _coordinator(
        ScriptedControllerProvider(_host_action_sequence()),
        environment_flags={"monitor": True},
    ).run(
        "Inspect CPU on monitor using Linux only.",
        hard_constraints=HardRequestConstraints(
            explicit_target=HardTargetReference("monitor", "monitor"),
            source_constraints=(SourceConstraint.LINUX,),
        ),
        session_store=store,
    )
    provider = ScriptedControllerProvider(
        [_decision(AgentDecisionKind.FINAL, answer="Unavailable.")]
    )
    follow_up = _coordinator(provider, environment_flags={"monitor": True}).run(
        "Còn network?", hard_constraints=HardRequestConstraints(), session_store=store
    )

    assert first.succeeded and follow_up.succeeded
    assert store.investigation_context.active_sources == (SourceConstraint.LINUX,)
    assert json.loads(provider.requests[0].user_prompt)["session_context"][
        "sources"
    ] == ["linux"]


def test_reset_and_unrelated_request_do_not_execute_or_erase_context(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )
    reset_provider = ScriptedControllerProvider([])

    reset = _coordinator(reset_provider).run(
        "reset context",
        hard_constraints=HardRequestConstraints(),
        session_store=store,
    )

    assert reset.succeeded
    assert store.investigation_context == SessionInvestigationContext()
    assert reset_provider.requests == []

    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )
    provider = ScriptedControllerProvider(
        [
            _decision(
                AgentDecisionKind.FINAL, answer="Prometheus is a monitoring system."
            )
        ]
    )
    result = _coordinator(provider).run(
        "What is Prometheus?",
        hard_constraints=HardRequestConstraints(),
        session_store=store,
    )

    assert result.succeeded
    assert "session_context" not in json.loads(provider.requests[0].user_prompt)
    assert store.investigation_context.active_target == "monitor"


def test_session_stores_remain_isolated_for_identical_follow_up(
    tmp_path: object,
) -> None:
    first_store = _session_store(tmp_path, "first")
    second_store = _session_store(tmp_path, "second")
    first_store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )
    first_provider = ScriptedControllerProvider(
        [_decision(AgentDecisionKind.FINAL, answer="Unavailable.")]
    )
    second_provider = ScriptedControllerProvider(
        [_decision(AgentDecisionKind.FINAL, answer="Unavailable.")]
    )

    _coordinator(first_provider, environment_flags={"monitor": True}).run(
        "Còn network?",
        hard_constraints=HardRequestConstraints(),
        session_store=first_store,
    )
    _coordinator(second_provider, environment_flags={"monitor": True}).run(
        "Còn network?",
        hard_constraints=HardRequestConstraints(),
        session_store=second_store,
    )

    assert (
        json.loads(first_provider.requests[0].user_prompt)["session_context"]["target"]
        == "monitor"
    )
    assert "session_context" not in json.loads(second_provider.requests[0].user_prompt)


def test_explicit_follow_up_target_is_not_repeated_as_stale_session_context(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )
    provider = ScriptedControllerProvider(_host_action_sequence())
    constraints = HardRequestConstraints(
        explicit_target=HardTargetReference("localhost", "localhost")
    )

    result = _coordinator(provider, environment_flags={"monitor": True}).run(
        "Còn CPU trên localhost?", hard_constraints=constraints, session_store=store
    )

    assert result.succeeded
    for request in provider.requests:
        payload = json.loads(request.user_prompt)
        constraints_payload = (
            payload.get("hard_constraints") or payload["run_state"]["hv"]
        )
        assert constraints_payload["target"]["registered_target"] == "localhost"
        assert payload.get("session_context", {}).get("target") != "monitor"
    assert any(
        observation.target_id == "localhost"
        for observation in result.run_state.observations
    )
    assert store.investigation_context.active_target == "localhost"


def test_explicit_follow_up_source_policy_hides_stale_session_sources(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    store.set_investigation_context(
        SessionInvestigationContext(
            active_target="monitor", active_sources=(SourceConstraint.GRAFANA,)
        )
    )
    provider = ScriptedControllerProvider(_host_action_sequence())
    constraints = HardRequestConstraints(
        source_constraints=(SourceConstraint.LINUX,),
    )

    result = _coordinator(provider, environment_flags={"monitor": True}).run(
        "Còn CPU thì sao?", hard_constraints=constraints, session_store=store
    )

    assert result.succeeded
    for request in provider.requests:
        payload = json.loads(request.user_prompt)
        constraints_payload = (
            payload.get("hard_constraints") or payload["run_state"]["hv"]
        )
        assert constraints_payload["sources"] == ["linux"]
        assert "sources" not in payload.get("session_context", {})
        assert "exclude" not in payload.get("session_context", {})


def test_only_source_bearing_validations_mark_inherited_source_completion_authority(
    tmp_path: object,
) -> None:
    store = _session_store(tmp_path)
    store.set_investigation_context(
        SessionInvestigationContext(active_sources=(SourceConstraint.GRAFANA,))
    )
    context = ControllerSessionContext(
        store, target_resolver=fake_environment().target_resolver
    )
    current = HardRequestConstraints()
    context.select("Còn CPU?", current)
    effective = context.action_constraints(current, None)

    context.record_validation(
        AgentActionValidationResult(
            AgentActionValidationStatus.VALID,
            AgentActionValidationReason.VALIDATED,
            "compute.deterministic",
            source_family="compute",
        ),
        current,
        effective,
    )

    assert context.completion_constraints(current).source_constraints == ()

    context.record_validation(
        AgentActionValidationResult(
            AgentActionValidationStatus.VALID,
            AgentActionValidationReason.VALIDATED,
            "grafana.get_metrics",
            source_family="grafana",
        ),
        current,
        effective,
    )

    assert context.completion_constraints(current).source_constraints == (
        SourceConstraint.GRAFANA,
    )
