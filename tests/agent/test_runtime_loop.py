from __future__ import annotations

import json

from src.agent.authority import (
    ActionAuthorizer,
    ApprovalScope,
    AuthorityBudget,
    ExactReferenceRegistry,
    ReferenceEntry,
)
from src.agent.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    DecisionKind,
    FinalClaim,
    FinalClaimKind,
)
from src.agent.discovery import CapabilityDiscovery
from src.agent.execution import (
    AgentExecutionResult,
    AuthorizedExecutionRequest,
    ExecutionStatus,
)
from src.agent.permissions import EffectClass, PermissionMode
from src.agent.runtime import (
    AgentRuntime,
    AgentRuntimeConfig,
    RuntimeFailureReason,
    RuntimeTerminal,
)
from src.model.agent_adapter import (
    AgentModelAdapter,
    AgentProviderRequest,
    AgentProviderResponse,
)
from src.model.agent_decision_controller import (
    AgentDecisionController,
)
from src.observability.events import AgentEventStore
from src.pipeline.calculator_action_contract import (
    CALCULATOR_CAPABILITY_ID,
    calculator_capability,
)


class ScriptedProvider:
    def __init__(
        self,
        decisions: list[AgentDecision | AgentProviderResponse | object],
    ) -> None:
        self.decisions = list(decisions)
        self.requests: list[AgentProviderRequest] = []

    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ) -> AgentProviderResponse:
        self.requests.append(request)

        if not self.decisions:
            raise AssertionError("No scripted decision remains.")

        payload = self.decisions.pop(0)
        if isinstance(payload, AgentProviderResponse):
            return payload
        return AgentProviderResponse(
            payload=(
                payload.to_wire() if isinstance(payload, AgentDecision) else payload
            ),
            provider="fake",
            model="fake-model",
        )


class FakeExecutor:
    def __init__(
        self,
        results: list[AgentExecutionResult] | None = None,
    ) -> None:
        self.requests: list[AuthorizedExecutionRequest] = []
        self.results = list(results or [])

    def execute(
        self,
        request: AuthorizedExecutionRequest,
    ) -> AgentExecutionResult:
        self.requests.append(request)

        if self.results:
            return self.results.pop(0)

        return AgentExecutionResult(
            status=ExecutionStatus.SUCCESS,
            dispatched=True,
            facts=(
                {
                    "metric": "cpu.percent",
                    "value": 30,
                },
            ),
            summary="Observation collected.",
            provenance={
                "source": request.target_ref or request.source_ref or "deterministic",
            },
        )


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "window": {
                "type": "integer",
                "minimum": 1,
                "maximum": 300,
            },
        },
        "required": ["window"],
    }


def _capability(
    capability_id: str = "host.cpu",
    *,
    effect: EffectClass = EffectClass.READ,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        purpose="Test capability",
        tool_id="linux",
        effect=effect,
        arguments_schema=_schema(),
        runtime_binding="test.execute",
        discovery_group="host",
        target_kind="machine",
        allowed_target_refs=frozenset({"monitor"}),
        available=True,
        safety_reviewed=True,
        budget_cost=2,
        result_kind="observation",
    )


def _runtime(
    decisions: list[AgentDecision | object],
    *,
    capabilities: tuple[CapabilityDefinition, ...] | None = None,
    executor: FakeExecutor | None = None,
    config: AgentRuntimeConfig | None = None,
    event_store: AgentEventStore | None = None,
) -> tuple[AgentRuntime, ScriptedProvider, FakeExecutor]:
    provider = ScriptedProvider(decisions)
    model = AgentModelAdapter([provider])

    capability_registry = CapabilityRegistry(capabilities or (_capability(),))

    targets = ExactReferenceRegistry((ReferenceEntry("monitor", "machine"),))
    sources = ExactReferenceRegistry(())

    discovery = CapabilityDiscovery(
        capability_registry,
        targets,
        sources,
    )
    authorizer = ActionAuthorizer(
        capability_registry,
        targets,
        sources,
    )
    controller = AgentDecisionController(
        model=model,
        discovery=discovery,
    )

    selected_executor = executor or FakeExecutor()

    runtime = AgentRuntime(
        controller=controller,
        discovery=discovery,
        authorizer=authorizer,
        capabilities=capability_registry,
        executor=selected_executor,
        config=config,
        event_store=event_store,
    )

    return runtime, provider, selected_executor


def _final(text: str = "Done.") -> AgentDecision:
    return AgentDecision(
        kind=DecisionKind.FINAL,
        goal="Answer.",
        answer=text,
    )


def _discover(category: str = "host") -> AgentDecision:
    return AgentDecision(
        kind=DecisionKind.DISCOVER,
        goal="Inspect CPU.",
        category=category,
    )


def _action(
    capability_id: str = "host.cpu",
    *,
    arguments: dict[str, object] | None = None,
) -> AgentDecision:
    return AgentDecision(
        kind=DecisionKind.ACTION,
        goal="Inspect CPU.",
        action=AgentAction(
            capability_id=capability_id,
            target_ref="monitor",
            arguments=arguments or {},
        ),
    )


def _calculator_capability() -> CapabilityDefinition:
    return calculator_capability()


def _calculator_arguments() -> dict[str, object]:
    return {
        "left": 287,
        "right": 419,
        "operation": "multiply",
    }


def _calculator_action(*, arguments: dict[str, object]) -> AgentDecision:
    return AgentDecision(
        kind=DecisionKind.ACTION,
        goal="Compute exactly.",
        action=AgentAction(
            capability_id=CALCULATOR_CAPABILITY_ID,
            arguments=arguments,
        ),
    )


def test_runtime_can_finish_directly_without_tools() -> None:
    runtime, provider, executor = _runtime([_final("Direct answer.")])

    result = runtime.run(
        "Hello.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.response_text == "Direct answer."
    assert result.model_calls == 1
    assert result.action_attempts == 0
    assert executor.requests == []
    assert len(provider.requests) == 1


def test_rejected_final_obligation_blocks_claimless_retry_until_calculator_evidence() -> (
    None
):
    evidence = {"result": 120253}
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.SUCCESS,
                dispatched=True,
                facts=(evidence,),
                summary="Calculation completed.",
                provenance={"source": "deterministic"},
            )
        ]
    )
    events = AgentEventStore()
    runtime, provider, _ = _runtime(
        [
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Compute exactly.",
                answer="120253",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.DETERMINISTIC_RESULT,
                        action_id=1,
                        capability_id=CALCULATOR_CAPABILITY_ID,
                        target_ref="target1",
                        source_ref="source1",
                        result={"result": 120253},
                    ),
                ),
            ),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Compute exactly.",
                answer="120253",
            ),
            AgentDecision(
                kind=DecisionKind.DISCOVER,
                goal="Compute exactly.",
                category="calculator",
            ),
            _calculator_action(arguments={}),
            _calculator_action(arguments=_calculator_arguments()),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Compute exactly.",
                answer="120253",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.DETERMINISTIC_RESULT,
                        action_id=1,
                        capability_id=CALCULATOR_CAPABILITY_ID,
                        result=evidence,
                    ),
                ),
            ),
        ],
        capabilities=(_calculator_capability(),),
        executor=executor,
        event_store=events,
    )

    result = runtime.run("Exact computation.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.response_text == "120253"
    assert result.model_calls == 6
    assert [request.capability_id for request in executor.requests] == [
        CALCULATOR_CAPABILITY_ID
    ]
    assert "completion_rejected" in provider.requests[1].user_prompt
    assert "evidence_missing" in provider.requests[1].user_prompt
    assert "completion_requirement_unresolved" in provider.requests[2].user_prompt
    recovery_schema = provider.requests[1].response_schema
    assert isinstance(recovery_schema["oneOf"], list)
    recovery_kinds: set[str] = set()
    for branch in recovery_schema["oneOf"]:
        assert isinstance(branch, dict)
        assert isinstance(branch["properties"], dict)
        assert isinstance(branch["properties"]["kind"], dict)
        assert isinstance(branch["properties"]["kind"]["enum"], list)
        kind_values = branch["properties"]["kind"]["enum"]
        assert len(kind_values) == 1
        assert isinstance(kind_values[0], str)
        recovery_kinds.add(kind_values[0])
    assert recovery_kinds == {"discover", "action", "clarify", "refuse"}
    rejected = [
        event for event in events.events() if event.event_type == "completion.rejected"
    ]
    assert [event.error_code for event in rejected] == [
        "evidence_missing",
        "completion_requirement_unresolved",
    ]
    assert rejected[0].capability_id is None
    assert rejected[0].target_ref is None
    assert rejected[0].source_ref is None
    assert dict(rejected[0].metadata) == {
        "claim_action_id": 1,
        "claim_capability_id": CALCULATOR_CAPABILITY_ID,
        "claim_kind": "deterministic_result",
    }


def test_calculator_discovery_action_evidence_and_final_claim_are_valid() -> None:
    evidence = {"value": "120253"}
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.SUCCESS,
                dispatched=True,
                facts=(evidence,),
                summary="Calculation completed.",
                provenance={"source": "deterministic"},
            )
        ]
    )
    runtime, provider, _ = _runtime(
        [
            AgentDecision(
                kind=DecisionKind.DISCOVER,
                goal="Compute exactly.",
                category="calculator",
            ),
            _calculator_action(arguments={}),
            _calculator_action(arguments=_calculator_arguments()),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Compute exactly.",
                answer="120253",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.DETERMINISTIC_RESULT,
                        action_id=1,
                        capability_id=CALCULATOR_CAPABILITY_ID,
                        result=evidence,
                    ),
                ),
            ),
        ],
        capabilities=(_calculator_capability(),),
        executor=executor,
    )

    result = runtime.run("Exact computation.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.response_text == "120253"
    assert [request.capability_id for request in executor.requests] == [
        CALCULATOR_CAPABILITY_ID
    ]
    assert executor.requests[0].target_ref is None
    assert executor.requests[0].source_ref is None
    assert result.observations[0].facts[0]["value"] == "120253"
    detail_request = provider.requests[2]
    detail_action = next(
        branch
        for branch in detail_request.response_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )["properties"]["action"]
    assert "target_ref" not in detail_action["properties"]
    assert "source_ref" not in detail_action["properties"]


def test_calculator_invented_target_is_rejected_without_execution() -> None:
    events = AgentEventStore()
    runtime, provider, executor = _runtime(
        [
            _discover("calculator"),
            _calculator_action(arguments={}),
            AgentDecision(
                kind=DecisionKind.ACTION,
                goal="Compute exactly.",
                action=AgentAction(
                    capability_id=CALCULATOR_CAPABILITY_ID,
                    target_ref="result",
                    arguments=_calculator_arguments(),
                ),
            ),
            _final("The target was not accepted."),
        ],
        capabilities=(_calculator_capability(),),
        event_store=events,
    )

    result = runtime.run("Compute exactly.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.action_attempts == 1
    assert executor.requests == []
    assert any(
        event.error_code == "target_not_allowed"
        for event in events.events()
        if event.event_type == "action.rejected"
    )
    detail_action = next(
        branch
        for branch in provider.requests[2].response_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )["properties"]["action"]
    assert "target_ref" not in detail_action["properties"]
    recovery_payload = json.loads(provider.requests[3].user_prompt)
    assert recovery_payload["observations"][0]["provenance"] == {
        "reference_constraints": {
            "target_ref": {"applicable": False},
            "source_ref": {"applicable": False},
        }
    }


def test_calculator_final_claim_rejects_mismatched_result_evidence() -> None:
    evidence = {"result": 120253}
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.SUCCESS,
                dispatched=True,
                facts=(evidence,),
                summary="Calculation completed.",
                provenance={"source": "deterministic"},
            )
        ]
    )
    events = AgentEventStore()
    runtime, provider, _ = _runtime(
        [
            AgentDecision(
                kind=DecisionKind.DISCOVER,
                goal="Compute exactly.",
                category="calculator",
            ),
            _calculator_action(arguments={}),
            _calculator_action(arguments=_calculator_arguments()),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Compute exactly.",
                answer="120853",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.DETERMINISTIC_RESULT,
                        action_id=1,
                        capability_id=CALCULATOR_CAPABILITY_ID,
                        result={"result": 120853},
                    ),
                ),
            ),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Compute exactly.",
                answer="120253",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.DETERMINISTIC_RESULT,
                        action_id=1,
                        capability_id=CALCULATOR_CAPABILITY_ID,
                        result=evidence,
                    ),
                ),
            ),
        ],
        capabilities=(_calculator_capability(),),
        executor=executor,
        event_store=events,
    )

    result = runtime.run("Exact computation.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.response_text == "120253"
    assert len(executor.requests) == 1
    assert "completion_rejected" in provider.requests[4].user_prompt
    assert "deterministic_result_mismatch" in provider.requests[4].user_prompt
    assert any(
        event.event_type == "completion.rejected"
        and event.error_code == "deterministic_result_mismatch"
        for event in events.events()
    )


def test_repeated_identical_rejected_final_stops_as_no_progress() -> None:
    invalid_final = AgentDecision(
        kind=DecisionKind.FINAL,
        goal="Compute exactly.",
        answer="120253",
        claims=(
            FinalClaim(
                kind=FinalClaimKind.DETERMINISTIC_RESULT,
                action_id=1,
                capability_id=CALCULATOR_CAPABILITY_ID,
                result={"result": 120253},
            ),
        ),
    )
    events = AgentEventStore()
    runtime, _, executor = _runtime(
        [invalid_final, _final("120253"), _final("120253")],
        capabilities=(_calculator_capability(),),
        config=AgentRuntimeConfig(
            max_model_calls=5,
            max_identical_invalid_decisions=2,
        ),
        event_store=events,
    )

    result = runtime.run("Exact computation.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FAILED
    assert result.failure is RuntimeFailureReason.NO_PROGRESS
    assert result.model_calls == 3
    assert executor.requests == []
    assert [
        event.error_code
        for event in events.events()
        if event.event_type == "completion.rejected"
    ] == [
        "evidence_missing",
        "completion_requirement_unresolved",
        "completion_requirement_unresolved",
    ]


def test_runtime_emits_discovery_execution_evidence_and_failure_events() -> None:
    events = AgentEventStore()
    runtime, _, _ = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
            _final(),
        ],
        event_store=events,
    )

    runtime.run(
        "Check CPU.",
        permission_mode=PermissionMode.READ,
        request_id="request-events",
        chat_id="chat-events",
        model_identity={"provider": "test", "model": "test-model"},
    )

    stream = events.events(request_id="request-events")
    event_types = [event.event_type for event in stream]

    assert {
        "model.started",
        "model.decision",
        "discovery.started",
        "discovery.completed",
        "action.proposed",
        "tool.started",
        "tool.completed",
        "evidence.created",
        "model.final",
    }.issubset(event_types)
    assert all(event.request_id == "request-events" for event in stream)
    assert all(event.chat_id == "chat-events" for event in stream)
    assert all(event.model == "test-model" for event in stream)
    assert events.metrics_snapshot()["execution_dispatches"] == 1
    assert events.metrics_snapshot()["successful_evidence"] == 1


def test_runtime_rejected_action_emits_no_successful_tool_event() -> None:
    events = AgentEventStore()
    runtime, _, _ = _runtime(
        [_discover(), _action(), _action(), _final()], event_store=events
    )

    runtime.run("Check CPU.", permission_mode=PermissionMode.READ, request_id="reject")

    stream = events.events(request_id="reject")
    assert any(event.event_type == "action.rejected" for event in stream)
    assert not any(
        event.event_type == "tool.completed" and event.status.value == "succeeded"
        for event in stream
    )
    assert events.metrics_snapshot()["action_rejections"] == 1
    assert events.metrics_snapshot()["execution_dispatches"] == 0


def test_runtime_failed_execution_does_not_count_as_successful_evidence() -> None:
    events = AgentEventStore()
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=True,
                reason="temporary_failure",
                recoverable=True,
            )
        ]
    )
    runtime, _, _ = _runtime(
        [_discover(), _action(), _action(arguments={"window": 60}), _final()],
        executor=executor,
        event_store=events,
    )

    runtime.run("Check CPU.", permission_mode=PermissionMode.READ, request_id="failed")

    stream = events.events(request_id="failed")
    assert any(event.event_type == "tool.failed" for event in stream)
    assert any(
        event.event_type == "evidence.created" and event.status.value == "failed"
        for event in stream
    )
    snapshot = events.metrics_snapshot()
    assert snapshot["execution_dispatches"] == 1
    assert snapshot["failed_tool_executions"] == 1
    assert snapshot["failed_evidence"] == 1
    assert snapshot["successful_evidence"] == 0


def test_runtime_model_failure_emits_model_failed() -> None:
    events = AgentEventStore()
    runtime, _, _ = _runtime([], event_store=events)

    result = runtime.run(
        "Check CPU.", permission_mode=PermissionMode.READ, request_id="model-failed"
    )

    assert result.failure is RuntimeFailureReason.MODEL_FAILURE
    assert [event.event_type for event in events.events(request_id="model-failed")] == [
        "model.started",
        "model.failed",
    ]


def test_model_failed_projects_provider_generation_diagnostics_for_events() -> None:
    events = AgentEventStore()
    runtime, _, _ = _runtime(
        [
            AgentProviderResponse(
                payload='{"kind":"action"',
                provider="qwen",
                model="qwen-test",
                generation_diagnostics={
                    "finish_reason": "length",
                    "usage_completion_tokens": 1024,
                    "usage_prompt_tokens": 312,
                    "stop_sequence_configured": False,
                    "content_bytes_before_sanitization": 1309,
                    "content_bytes_after_sanitization": 1309,
                    "provider_http_status": 200,
                },
            )
        ],
        event_store=events,
    )

    result = runtime.run("Compute exactly.", permission_mode=PermissionMode.READ)

    assert result.failure is RuntimeFailureReason.MODEL_FAILURE
    failed = [event for event in events.events() if event.event_type == "model.failed"]
    assert len(failed) == 1
    provider_generation = failed[0].to_dict()["metadata"]["parse_diagnostics"][
        "provider_generation"
    ]
    assert provider_generation == {
        "finish_reason": "length",
        "completion_count": 1024,
        "prompt_count": 312,
        "stop_sequence_configured": False,
        "content_bytes_before_sanitization": 1309,
        "content_bytes_after_sanitization": 1309,
        "provider_http_status": 200,
    }
    assert not any(
        "token" in key.casefold()
        for key in _metadata_keys(failed[0].to_dict()["metadata"])
    )


def _metadata_keys(value: object) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    nested = tuple(key for item in value.values() for key in _metadata_keys(item))
    return tuple(value) + nested


def test_selected_action_detail_invalid_output_emits_safe_parser_diagnostics() -> None:
    malformed_action = {
        "version": 3,
        "kind": "action",
        "action": {
            "capability_id": CALCULATOR_CAPABILITY_ID,
            "arguments": _calculator_arguments(),
            "unexpected": True,
        },
    }
    events = AgentEventStore()
    runtime, _, executor = _runtime(
        [
            AgentDecision(
                kind=DecisionKind.DISCOVER,
                goal="Compute exactly.",
                category="calculator",
            ),
            _calculator_action(arguments={}),
            malformed_action,
        ],
        capabilities=(_calculator_capability(),),
        event_store=events,
    )

    result = runtime.run("Compute exactly.", permission_mode=PermissionMode.READ)

    assert result.failure is RuntimeFailureReason.MODEL_FAILURE
    assert result.model_calls == 3
    assert result.action_attempts == 0
    assert executor.requests == []
    failed = [event for event in events.events() if event.event_type == "model.failed"]
    assert len(failed) == 1
    assert failed[0].error_code == "invalid_output"
    assert failed[0].to_dict()["metadata"]["parse_diagnostics"] == {
        "response_type": "dict",
        "response_length": None,
        "parse_error_category": "contract_error",
        "schema_validation_error_path": None,
        "parser_error_path": "action",
        "json_top_level_keys": [
            "action",
            "kind",
            "version",
        ],
        "unknown_top_level_key_count": 0,
        "decision_kind": "action",
    }


def test_final_claim_reference_mismatch_returns_recoverable_feedback() -> None:
    runtime, provider, _ = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Report CPU.",
                answer="CPU was collected.",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.OBSERVATION,
                        action_id=1,
                        capability_id="host.cpu",
                        target_ref="wrong-target",
                    ),
                ),
            ),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Report CPU.",
                answer="CPU was collected.",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.OBSERVATION,
                        action_id=1,
                        capability_id="host.cpu",
                        target_ref="monitor",
                    ),
                ),
            ),
        ]
    )

    result = runtime.run("Check CPU.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FINAL
    assert "completion_rejected" in provider.requests[4].user_prompt
    assert "reference_mismatch" in provider.requests[4].user_prompt


def test_final_deterministic_claim_result_mismatch_returns_recoverable_feedback() -> (
    None
):
    runtime, provider, _ = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Report CPU.",
                answer="CPU was collected.",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.DETERMINISTIC_RESULT,
                        action_id=1,
                        capability_id="host.cpu",
                        target_ref="monitor",
                        result={"logical_cores": 999},
                    ),
                ),
            ),
            AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Report CPU.",
                answer="CPU was collected.",
                claims=(
                    FinalClaim(
                        kind=FinalClaimKind.DETERMINISTIC_RESULT,
                        action_id=1,
                        capability_id="host.cpu",
                        target_ref="monitor",
                        result={"metric": "cpu.percent", "value": 30},
                    ),
                ),
            ),
        ]
    )

    result = runtime.run("Check CPU.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FINAL
    assert "completion_rejected" in provider.requests[4].user_prompt
    assert "deterministic_result_mismatch" in provider.requests[4].user_prompt


def test_runtime_progressive_discovery_authority_execution_loop() -> None:
    runtime, provider, executor = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
            _final("CPU looks fine."),
        ]
    )

    result = runtime.run(
        "Check monitor CPU.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.response_text == "CPU looks fine."
    assert result.model_calls == 4
    assert result.discovery_calls == 1
    assert result.action_attempts == 1

    assert len(executor.requests) == 1

    request = executor.requests[0]
    assert request.capability_id == "host.cpu"
    assert request.target_ref == "monitor"
    assert dict(request.arguments) == {"window": 60}

    assert result.budget.actions_used == 1
    assert result.budget.cost_used == 2
    assert len(result.observations) == 1
    assert result.observations[0].capability_id == "host.cpu"
    discovery_payload = json.loads(provider.requests[1].user_prompt)
    assert discovery_payload["capabilities"][0]["capability_id"] == "host.cpu"
    discovery_schema = provider.requests[1].response_schema
    assert all(
        branch["properties"]["kind"]["enum"] != ["discover"]
        for branch in discovery_schema["oneOf"]
    )
    action_branch = next(
        branch
        for branch in discovery_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )
    assert action_branch["properties"]["action"]["properties"]["capability_id"] == {
        "type": "string",
        "enum": ["host.cpu"],
    }


def test_discovery_of_another_undisclosed_group_remains_legal() -> None:
    runtime, provider, _ = _runtime(
        [
            _discover("host"),
            _discover("calculator"),
            _final("Done."),
        ],
        capabilities=(_capability(), _calculator_capability()),
    )

    result = runtime.run("Investigate.", permission_mode=PermissionMode.READ)

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.discovery_calls == 2
    first_discovery_schema = provider.requests[1].response_schema
    discover_branch = next(
        branch
        for branch in first_discovery_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["discover"]
    )
    assert discover_branch["properties"]["category"] == {
        "type": "string",
        "enum": ["calculator"],
    }


def test_unknown_capability_returns_feedback_without_execution() -> None:
    runtime, provider, executor = _runtime(
        [
            _discover(),
            _action("host.unknown"),
            _final("Cannot use that capability."),
        ]
    )

    result = runtime.run(
        "Check something.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.model_calls == 3
    assert executor.requests == []

    feedback = provider.requests[2].user_prompt
    assert "capability_not_disclosed" in feedback


def test_first_stage_action_is_rejected_without_registry_detail_disclosure() -> None:
    runtime, provider, executor = _runtime(
        [
            _action(),
            _final("I need to discover a capability first."),
        ]
    )

    result = runtime.run(
        "Check something.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert executor.requests == []
    assert "invalid_decision" in provider.requests[1].user_prompt
    assert "action_not_allowed_in_first" in provider.requests[1].user_prompt


def test_registry_capability_is_not_authority_until_group_was_disclosed() -> None:
    runtime, provider, executor = _runtime(
        [
            _action(),
            _final("Capability was not disclosed."),
        ]
    )

    result = runtime.run(
        "Check something.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert executor.requests == []
    assert "capability_not_disclosed" not in provider.requests[1].user_prompt


def test_repeated_invalid_stage_decisions_stop_as_no_progress() -> None:
    runtime, _, executor = _runtime(
        [_action(), _action(), _action()],
        config=AgentRuntimeConfig(max_identical_invalid_decisions=2),
    )

    result = runtime.run(
        "Check something.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FAILED
    assert result.failure is RuntimeFailureReason.NO_PROGRESS
    assert result.model_calls == 3
    assert executor.requests == []


def test_read_mode_blocks_write_without_execution() -> None:
    write = _capability(
        "host.restart",
        effect=EffectClass.WRITE,
    )

    runtime, _, executor = _runtime(
        [
            _discover(),
            _action("host.restart"),
            _action(
                "host.restart",
                arguments={"window": 60},
            ),
            _final("Write is blocked."),
        ],
        capabilities=(write,),
    )

    result = runtime.run(
        "Restart monitor.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert executor.requests == []
    assert len(result.observations) == 1
    assert result.observations[0].reason == "effect_blocked"


def test_rw_ask_stops_for_approval_before_execution() -> None:
    write = _capability(
        "host.restart",
        effect=EffectClass.WRITE,
    )

    runtime, _, executor = _runtime(
        [
            _discover(),
            _action("host.restart"),
            _action(
                "host.restart",
                arguments={"window": 60},
            ),
        ],
        capabilities=(write,),
    )

    result = runtime.run(
        "Restart monitor.",
        permission_mode=PermissionMode.RW_ASK,
    )

    assert result.terminal is RuntimeTerminal.APPROVAL_REQUIRED
    assert result.pending_action is not None
    assert result.pending_authorization is not None
    assert executor.requests == []
    assert result.budget.actions_used == 0


def test_exact_rw_ask_approval_allows_execution() -> None:
    write = _capability(
        "host.restart",
        effect=EffectClass.WRITE,
    )

    runtime, _, executor = _runtime(
        [
            _discover(),
            _action("host.restart"),
            _action(
                "host.restart",
                arguments={"window": 60},
            ),
            _final("Restart completed."),
        ],
        capabilities=(write,),
    )

    result = runtime.run(
        "Restart monitor.",
        permission_mode=PermissionMode.RW_ASK,
        approval=ApprovalScope(
            approval_id="approval-1",
            goal="Restart monitor.",
            capability_ids=frozenset({"host.restart"}),
            target_refs=frozenset({"monitor"}),
        ),
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert len(executor.requests) == 1
    assert result.budget.actions_used == 1


def test_budget_consumes_only_when_executor_dispatches() -> None:
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.UNAVAILABLE,
                dispatched=False,
                reason="binding_unavailable",
                recoverable=True,
            )
        ]
    )

    runtime, _, _ = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
            _final("No binding."),
        ],
        executor=executor,
    )

    result = runtime.run(
        "Check CPU.",
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(
            max_actions=2,
            max_cost=4,
        ),
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.budget.actions_used == 0
    assert result.budget.cost_used == 0


def test_repeated_identical_action_triggers_no_progress_breaker() -> None:
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=True,
                reason="temporary_error",
                recoverable=True,
            )
        ]
    )

    runtime, _, _ = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
            _action(),
            _action(arguments={"window": 60}),
        ],
        executor=executor,
        config=AgentRuntimeConfig(
            max_identical_actions=1,
        ),
    )

    result = runtime.run(
        "Check CPU.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FAILED
    assert result.failure is RuntimeFailureReason.NO_PROGRESS
    assert len(executor.requests) == 1


def test_repeated_disclosed_group_stops_as_no_progress_without_spending_budget() -> (
    None
):
    runtime, provider, _ = _runtime(
        [
            _discover(),
            _discover(),
            _discover(),
            _discover(),
        ],
        config=AgentRuntimeConfig(
            max_discovery_calls=3,
            max_identical_invalid_decisions=2,
        ),
    )

    result = runtime.run(
        "Investigate.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FAILED
    assert result.failure is RuntimeFailureReason.NO_PROGRESS
    assert result.discovery_calls == 1
    assert result.model_calls == 4
    assert "capability_group_already_disclosed" in provider.requests[2].user_prompt


def test_secret_shaped_execution_observation_fails_before_next_model_call() -> None:
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.SUCCESS,
                dispatched=True,
                facts=(
                    {
                        "token": "must-not-reach-model",
                    },
                ),
            )
        ]
    )

    runtime, provider, _ = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
        ],
        executor=executor,
    )

    result = runtime.run(
        "Check CPU.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FAILED
    assert result.failure is RuntimeFailureReason.CONTRACT_FAILURE

    # Discovery + first proposal + selected-schema action only.
    # No provider request containing the secret observation was sent.
    assert len(provider.requests) == 3


def test_runtime_rejects_mixed_registry_composition() -> None:
    provider = ScriptedProvider([_final()])
    model = AgentModelAdapter([provider])

    caps_a = CapabilityRegistry((_capability(),))
    caps_b = CapabilityRegistry((_capability(),))

    targets = ExactReferenceRegistry((ReferenceEntry("monitor", "machine"),))
    sources = ExactReferenceRegistry(())

    discovery = CapabilityDiscovery(
        caps_a,
        targets,
        sources,
    )
    controller = AgentDecisionController(
        model=model,
        discovery=discovery,
    )
    authorizer = ActionAuthorizer(
        caps_b,
        targets,
        sources,
    )

    import pytest

    with pytest.raises(
        ValueError,
        match="one capability registry",
    ):
        AgentRuntime(
            controller=controller,
            discovery=discovery,
            authorizer=authorizer,
            capabilities=caps_a,
            executor=FakeExecutor(),
        )


def test_budget_consumes_failed_action_after_dispatch() -> None:
    executor = FakeExecutor(
        [
            AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=True,
                reason="temporary_failure",
                recoverable=True,
            )
        ]
    )

    runtime, _, _ = _runtime(
        [
            _discover(),
            _action(),
            _action(arguments={"window": 60}),
            _final("Execution failed."),
        ],
        executor=executor,
    )

    result = runtime.run(
        "Check CPU.",
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(
            max_actions=2,
            max_cost=4,
        ),
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.budget.actions_used == 1
    assert result.budget.cost_used == 2
