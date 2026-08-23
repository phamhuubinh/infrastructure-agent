from __future__ import annotations

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


class ScriptedProvider:
    def __init__(
        self,
        decisions: list[AgentDecision],
    ) -> None:
        self.decisions = list(decisions)
        self.requests: list[AgentProviderRequest] = []

    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ) -> AgentProviderResponse:
        self.requests.append(request)

        if not self.decisions:
            raise AssertionError(
                "No scripted decision remains."
            )

        return AgentProviderResponse(
            payload=self.decisions.pop(0).to_wire(),
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
                "source": request.target_ref
                or request.source_ref
                or "deterministic",
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
    decisions: list[AgentDecision],
    *,
    capabilities: tuple[CapabilityDefinition, ...] | None = None,
    executor: FakeExecutor | None = None,
    config: AgentRuntimeConfig | None = None,
) -> tuple[AgentRuntime, ScriptedProvider, FakeExecutor]:
    provider = ScriptedProvider(decisions)
    model = AgentModelAdapter([provider])

    capability_registry = CapabilityRegistry(
        capabilities or (_capability(),)
    )

    targets = ExactReferenceRegistry(
        (
            ReferenceEntry("monitor", "machine"),
        )
    )
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
    )

    return runtime, provider, selected_executor


def _final(text: str = "Done.") -> AgentDecision:
    return AgentDecision(
        kind=DecisionKind.FINAL,
        goal="Answer.",
        answer=text,
    )


def _discover() -> AgentDecision:
    return AgentDecision(
        kind=DecisionKind.DISCOVER,
        goal="Inspect CPU.",
        category="host",
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


def test_runtime_can_finish_directly_without_tools() -> None:
    runtime, provider, executor = _runtime(
        [_final("Direct answer.")]
    )

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


def test_runtime_progressive_discovery_authority_execution_loop() -> None:
    runtime, _, executor = _runtime(
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


def test_unknown_capability_returns_feedback_without_execution() -> None:
    runtime, provider, executor = _runtime(
        [
            _action("host.unknown"),
            _final("Cannot use that capability."),
        ]
    )

    result = runtime.run(
        "Check something.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.model_calls == 2
    assert executor.requests == []

    feedback = provider.requests[1].user_prompt
    assert "unknown_capability" in feedback


def test_read_mode_blocks_write_without_execution() -> None:
    write = _capability(
        "host.restart",
        effect=EffectClass.WRITE,
    )

    runtime, _, executor = _runtime(
        [
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

    assert (
        result.terminal
        is RuntimeTerminal.APPROVAL_REQUIRED
    )
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
            capability_ids=frozenset(
                {"host.restart"}
            ),
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
    assert (
        result.failure
        is RuntimeFailureReason.NO_PROGRESS
    )
    assert len(executor.requests) == 1


def test_discovery_limit_is_harness_owned() -> None:
    runtime, _, _ = _runtime(
        [
            _discover(),
            _discover(),
        ],
        config=AgentRuntimeConfig(
            max_discovery_calls=1,
        ),
    )

    result = runtime.run(
        "Investigate.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FAILED
    assert (
        result.failure
        is RuntimeFailureReason.DISCOVERY_LIMIT
    )


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
    assert (
        result.failure
        is RuntimeFailureReason.CONTRACT_FAILURE
    )

    # First proposal + selected-schema action only.
    # No provider request containing the secret observation was sent.
    assert len(provider.requests) == 2


def test_runtime_rejects_mixed_registry_composition() -> None:
    provider = ScriptedProvider([_final()])
    model = AgentModelAdapter([provider])

    caps_a = CapabilityRegistry((_capability(),))
    caps_b = CapabilityRegistry((_capability(),))

    targets = ExactReferenceRegistry(
        (ReferenceEntry("monitor", "machine"),)
    )
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
