"""Dedicated canonical Orion agent runtime loop."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.agent.authority import (
    ActionAuthorizer,
    ApprovalScope,
    AuthorizationResult,
    AuthorizationStatus,
    AuthorityBudget,
)
from src.agent.capabilities import CapabilityRegistry
from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    AgentObservation,
    DecisionKind,
)
from src.agent.discovery import (
    CapabilityDetailStatus,
    CapabilityDiscovery,
    DiscoveryStatus,
)
from src.agent.execution import (
    AgentExecutionResult,
    AuthorizedActionExecutor,
    AuthorizedExecutionRequest,
    authorization_observation,
)
from src.agent.permissions import PermissionMode
from src.model.agent_adapter import (
    AgentDecisionResult,
    AgentModelError,
)


@runtime_checkable
class AgentDecisionDriver(Protocol):
    @property
    def discovery(self) -> CapabilityDiscovery: ...

    def decide_first(
        self,
        request: str,
        *,
        request_id: str | None = None,
    ) -> AgentDecisionResult: ...

    def decide_after_discovery(
        self,
        request: str,
        *,
        group: str,
        request_id: str | None = None,
    ) -> AgentDecisionResult: ...

    def decide_with_action_detail(
        self,
        request: str,
        *,
        proposed_action: AgentAction,
        request_id: str | None = None,
    ) -> AgentDecisionResult: ...

    def decide_after_observation(
        self,
        request: str,
        *,
        observations: Sequence[AgentObservation],
        request_id: str | None = None,
    ) -> AgentDecisionResult: ...

    def decide_after_feedback(
        self,
        request: str,
        *,
        feedback: Mapping[str, object],
        request_id: str | None = None,
    ) -> AgentDecisionResult: ...


class RuntimeTerminal(str, Enum):
    FINAL = "final"
    CLARIFY = "clarify"
    REFUSE = "refuse"
    APPROVAL_REQUIRED = "approval_required"
    FAILED = "failed"


class RuntimeFailureReason(str, Enum):
    MODEL_FAILURE = "model_failure"
    MODEL_CALL_LIMIT = "model_call_limit"
    DISCOVERY_LIMIT = "discovery_limit"
    ACTION_LIMIT = "action_limit"
    NO_PROGRESS = "no_progress"
    CONTRACT_FAILURE = "contract_failure"
    EXECUTOR_FAILURE = "executor_failure"


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_model_calls: int = 8
    max_discovery_calls: int = 3
    max_action_attempts: int = 6
    max_identical_actions: int = 2
    max_retained_observations: int = 12

    def __post_init__(self) -> None:
        for field_name, maximum in (
            ("max_model_calls", 32),
            ("max_discovery_calls", 16),
            ("max_action_attempts", 16),
            ("max_identical_actions", 4),
            ("max_retained_observations", 12),
        ):
            value = getattr(self, field_name)
            if (
                type(value) is not int
                or value < 1
                or value > maximum
            ):
                raise ValueError(
                    f"{field_name} must be between 1 and {maximum}."
                )


@dataclass(frozen=True, slots=True)
class AgentRuntimeResult:
    terminal: RuntimeTerminal
    response_text: str
    observations: tuple[AgentObservation, ...]
    budget: AuthorityBudget
    model_calls: int
    discovery_calls: int
    action_attempts: int
    failure: RuntimeFailureReason | None = None
    pending_action: AgentAction | None = None
    pending_authorization: AuthorizationResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.terminal, RuntimeTerminal):
            raise TypeError("terminal must be RuntimeTerminal.")

        if not isinstance(self.response_text, str) or not self.response_text:
            raise ValueError(
                "response_text must be non-empty."
            )

        if self.terminal is RuntimeTerminal.FAILED:
            if self.failure is None:
                raise ValueError(
                    "failed runtime result requires failure."
                )
        elif self.failure is not None:
            raise ValueError(
                "non-failed runtime result must not contain failure."
            )

        if self.terminal is RuntimeTerminal.APPROVAL_REQUIRED:
            if (
                self.pending_action is None
                or self.pending_authorization is None
            ):
                raise ValueError(
                    "approval result requires pending action and authorization."
                )


class _RuntimeStop(RuntimeError):
    def __init__(self, reason: RuntimeFailureReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class AgentRuntime:
    """Run model -> authority -> execution -> observation until terminal."""

    def __init__(
        self,
        *,
        controller: AgentDecisionDriver,
        discovery: CapabilityDiscovery,
        authorizer: ActionAuthorizer,
        capabilities: CapabilityRegistry,
        executor: AuthorizedActionExecutor,
        config: AgentRuntimeConfig | None = None,
    ) -> None:
        if not isinstance(controller, AgentDecisionDriver):
            raise TypeError(
                "controller must implement AgentDecisionDriver."
            )

        if not isinstance(discovery, CapabilityDiscovery):
            raise TypeError(
                "discovery must be CapabilityDiscovery."
            )

        if not isinstance(authorizer, ActionAuthorizer):
            raise TypeError(
                "authorizer must be ActionAuthorizer."
            )

        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError(
                "capabilities must be CapabilityRegistry."
            )

        if not isinstance(executor, AuthorizedActionExecutor):
            raise TypeError(
                "executor must implement AuthorizedActionExecutor."
            )

        if controller.discovery is not discovery:
            raise ValueError(
                "controller and runtime must share one discovery instance."
            )

        if discovery.capabilities is not capabilities:
            raise ValueError(
                "discovery and runtime must share one capability registry."
            )

        if authorizer.capabilities is not capabilities:
            raise ValueError(
                "authorizer and runtime must share one capability registry."
            )

        if authorizer.targets is not discovery.targets:
            raise ValueError(
                "authorizer and discovery must share one target registry."
            )

        if authorizer.sources is not discovery.sources:
            raise ValueError(
                "authorizer and discovery must share one source registry."
            )

        if config is not None and not isinstance(
            config,
            AgentRuntimeConfig,
        ):
            raise TypeError(
                "config must be AgentRuntimeConfig or None."
            )

        self._controller = controller
        self._discovery = discovery
        self._authorizer = authorizer
        self._capabilities = capabilities
        self._executor = executor
        self._config = config or AgentRuntimeConfig()

    def run(
        self,
        request: str,
        *,
        permission_mode: PermissionMode,
        budget: AuthorityBudget | None = None,
        approval: ApprovalScope | None = None,
        request_id: str | None = None,
    ) -> AgentRuntimeResult:
        if not isinstance(request, str) or not request.strip():
            raise ValueError(
                "request must be non-empty text."
            )

        if not isinstance(permission_mode, PermissionMode):
            raise TypeError(
                "permission_mode must be PermissionMode."
            )

        current_budget = budget or AuthorityBudget()

        if not isinstance(current_budget, AuthorityBudget):
            raise TypeError(
                "budget must be AuthorityBudget or None."
            )

        observations: list[AgentObservation] = []
        model_calls = 0
        discovery_calls = 0
        action_attempts = 0
        action_id = 0

        disclosed_capability: str | None = None
        last_action_fingerprint: str | None = None
        identical_action_count = 0

        def call_model(method, /, *args, **kwargs):
            nonlocal model_calls

            if model_calls >= self._config.max_model_calls:
                raise _RuntimeStop(
                    RuntimeFailureReason.MODEL_CALL_LIMIT
                )

            model_calls += 1
            return method(*args, **kwargs)

        def retained() -> tuple[AgentObservation, ...]:
            return tuple(
                observations[
                    -self._config.max_retained_observations :
                ]
            )

        try:
            decision_result = call_model(
                self._controller.decide_first,
                request,
                request_id=request_id,
            )

            while True:
                decision = decision_result.decision

                if decision.kind is DecisionKind.FINAL:
                    return self._result(
                        RuntimeTerminal.FINAL,
                        decision.answer or "",
                        observations,
                        current_budget,
                        model_calls,
                        discovery_calls,
                        action_attempts,
                    )

                if decision.kind is DecisionKind.CLARIFY:
                    return self._result(
                        RuntimeTerminal.CLARIFY,
                        decision.question or "",
                        observations,
                        current_budget,
                        model_calls,
                        discovery_calls,
                        action_attempts,
                    )

                if decision.kind is DecisionKind.REFUSE:
                    return self._result(
                        RuntimeTerminal.REFUSE,
                        decision.reason or "",
                        observations,
                        current_budget,
                        model_calls,
                        discovery_calls,
                        action_attempts,
                    )

                if decision.kind is DecisionKind.DISCOVER:
                    disclosed_capability = None
                    discovery_calls += 1

                    if (
                        discovery_calls
                        > self._config.max_discovery_calls
                    ):
                        raise _RuntimeStop(
                            RuntimeFailureReason.DISCOVERY_LIMIT
                        )

                    group = decision.category or ""
                    result = self._discovery.discover(group)

                    if result.status is DiscoveryStatus.DISCOVERED:
                        decision_result = call_model(
                            self._controller.decide_after_discovery,
                            request,
                            group=group,
                            request_id=request_id,
                        )
                    else:
                        decision_result = call_model(
                            self._controller.decide_after_feedback,
                            request,
                            feedback={
                                "status": "invalid_discovery",
                                "reason": result.status.value,
                                "group": group,
                            },
                            request_id=request_id,
                        )

                    continue

                if decision.kind is not DecisionKind.ACTION:
                    raise _RuntimeStop(
                        RuntimeFailureReason.CONTRACT_FAILURE
                    )

                action = decision.action

                if action is None:
                    raise _RuntimeStop(
                        RuntimeFailureReason.CONTRACT_FAILURE
                    )

                if disclosed_capability != action.capability_id:
                    detail = self._discovery.selected_detail(
                        action.capability_id
                    )

                    if (
                        detail.status
                        is not CapabilityDetailStatus.DISCLOSED
                    ):
                        disclosed_capability = None
                        decision_result = call_model(
                            self._controller.decide_after_feedback,
                            request,
                            feedback={
                                "status": "invalid_action",
                                "reason": detail.status.value,
                                "capability_id": action.capability_id,
                            },
                            request_id=request_id,
                        )
                        continue

                    decision_result = call_model(
                        self._controller.decide_with_action_detail,
                        request,
                        proposed_action=action,
                        request_id=request_id,
                    )
                    disclosed_capability = action.capability_id
                    continue

                # ACTION returned under the selected capability's closed schema.
                disclosed_capability = None
                action_attempts += 1

                if (
                    action_attempts
                    > self._config.max_action_attempts
                ):
                    raise _RuntimeStop(
                        RuntimeFailureReason.ACTION_LIMIT
                    )

                fingerprint = _action_fingerprint(action)

                if fingerprint == last_action_fingerprint:
                    identical_action_count += 1
                else:
                    last_action_fingerprint = fingerprint
                    identical_action_count = 1

                if (
                    identical_action_count
                    > self._config.max_identical_actions
                ):
                    raise _RuntimeStop(
                        RuntimeFailureReason.NO_PROGRESS
                    )

                authorization = self._authorizer.authorize(
                    action,
                    permission_mode=permission_mode,
                    budget=current_budget,
                    approval=approval,
                )

                action_id += 1

                if (
                    authorization.status
                    is AuthorizationStatus.APPROVAL_REQUIRED
                ):
                    return AgentRuntimeResult(
                        terminal=RuntimeTerminal.APPROVAL_REQUIRED,
                        response_text=(
                            "Approval is required before this write action "
                            "can execute."
                        ),
                        observations=retained(),
                        budget=current_budget,
                        model_calls=model_calls,
                        discovery_calls=discovery_calls,
                        action_attempts=action_attempts,
                        pending_action=action,
                        pending_authorization=authorization,
                    )

                if not authorization.valid:
                    observations.append(
                        authorization_observation(
                            action_id,
                            authorization,
                        )
                    )

                    decision_result = call_model(
                        self._controller.decide_after_observation,
                        request,
                        observations=retained(),
                        request_id=request_id,
                    )
                    continue

                capability = self._capabilities.get(
                    authorization.capability_id
                )

                if capability is None:
                    raise _RuntimeStop(
                        RuntimeFailureReason.CONTRACT_FAILURE
                    )

                execution_request = (
                    AuthorizedExecutionRequest.from_authorization(
                        capability,
                        authorization,
                    )
                )

                try:
                    execution = self._executor.execute(
                        execution_request
                    )
                except Exception as exc:
                    raise _RuntimeStop(
                        RuntimeFailureReason.EXECUTOR_FAILURE
                    ) from exc

                if not isinstance(
                    execution,
                    AgentExecutionResult,
                ):
                    raise _RuntimeStop(
                        RuntimeFailureReason.EXECUTOR_FAILURE
                    )

                if execution.dispatched:
                    current_budget = (
                        current_budget.after_execution(
                            authorization.budget_cost
                        )
                    )

                observations.append(
                    execution.to_observation(
                        action_id,
                        execution_request,
                    )
                )

                decision_result = call_model(
                    self._controller.decide_after_observation,
                    request,
                    observations=retained(),
                    request_id=request_id,
                )

        except AgentModelError:
            return self._failure_result(
                RuntimeFailureReason.MODEL_FAILURE,
                observations,
                current_budget,
                model_calls,
                discovery_calls,
                action_attempts,
            )
        except _RuntimeStop as exc:
            return self._failure_result(
                exc.reason,
                observations,
                current_budget,
                model_calls,
                discovery_calls,
                action_attempts,
            )
        except (TypeError, ValueError):
            return self._failure_result(
                RuntimeFailureReason.CONTRACT_FAILURE,
                observations,
                current_budget,
                model_calls,
                discovery_calls,
                action_attempts,
            )

    @staticmethod
    def _result(
        terminal: RuntimeTerminal,
        response_text: str,
        observations: list[AgentObservation],
        budget: AuthorityBudget,
        model_calls: int,
        discovery_calls: int,
        action_attempts: int,
    ) -> AgentRuntimeResult:
        return AgentRuntimeResult(
            terminal=terminal,
            response_text=response_text,
            observations=tuple(observations),
            budget=budget,
            model_calls=model_calls,
            discovery_calls=discovery_calls,
            action_attempts=action_attempts,
        )

    @staticmethod
    def _failure_result(
        failure: RuntimeFailureReason,
        observations: list[AgentObservation],
        budget: AuthorityBudget,
        model_calls: int,
        discovery_calls: int,
        action_attempts: int,
    ) -> AgentRuntimeResult:
        message = {
            RuntimeFailureReason.MODEL_FAILURE:
                "The model could not produce a valid next step.",
            RuntimeFailureReason.MODEL_CALL_LIMIT:
                "The agent stopped after reaching its model-call limit.",
            RuntimeFailureReason.DISCOVERY_LIMIT:
                "The agent stopped after reaching its discovery limit.",
            RuntimeFailureReason.ACTION_LIMIT:
                "The agent stopped after reaching its action limit.",
            RuntimeFailureReason.NO_PROGRESS:
                "The agent stopped because it was not making progress.",
            RuntimeFailureReason.CONTRACT_FAILURE:
                "The agent stopped because a runtime contract was invalid.",
            RuntimeFailureReason.EXECUTOR_FAILURE:
                "The agent stopped because execution could not be completed.",
        }[failure]

        return AgentRuntimeResult(
            terminal=RuntimeTerminal.FAILED,
            response_text=message,
            observations=tuple(observations),
            budget=budget,
            model_calls=model_calls,
            discovery_calls=discovery_calls,
            action_attempts=action_attempts,
            failure=failure,
        )


def _action_fingerprint(action: AgentAction) -> str:
    payload = action.to_wire()
    payload.pop("activity_text", None)

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


__all__ = [
    "AgentDecisionDriver",
    "AgentRuntime",
    "AgentRuntimeConfig",
    "AgentRuntimeResult",
    "RuntimeFailureReason",
    "RuntimeTerminal",
]
