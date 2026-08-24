"""Dedicated canonical Orion agent runtime loop."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable

from src.agent.authority import (
    ActionAuthorizer,
    ApprovalScope,
    AuthorityBudget,
    AuthorizationReason,
    AuthorizationResult,
    AuthorizationStatus,
)
from src.agent.capabilities import CapabilityRegistry
from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    AgentObservation,
    DecisionKind,
    FinalClaim,
    FinalClaimKind,
)
from src.agent.discovery import (
    CapabilityDetailStatus,
    CapabilityDiscovery,
    DiscoveryResult,
    DiscoveryStatus,
)
from src.agent.execution import (
    AgentExecutionResult,
    AuthorizedActionExecutor,
    AuthorizedExecutionRequest,
    ExecutionStatus,
    authorization_observation,
)
from src.agent.permissions import PermissionMode
from src.model.agent_adapter import (
    AgentDecisionResult,
    AgentModelError,
)
from src.observability.events import (
    AgentEvent,
    AgentEventStore,
    EventStatus,
    get_event_store,
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
        result: DiscoveryResult,
        additional_capability_groups: Sequence[str],
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


class _DecisionStage(str, Enum):
    FIRST = "first"
    DISCOVERY = "discovery"
    ACTION_DETAIL = "action_detail"
    OBSERVATION = "observation"
    FEEDBACK = "feedback"


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_model_calls: int = 8
    max_discovery_calls: int = 3
    max_action_attempts: int = 6
    max_identical_actions: int = 2
    max_identical_invalid_decisions: int = 2
    max_retained_observations: int = 12

    def __post_init__(self) -> None:
        for field_name, maximum in (
            ("max_model_calls", 32),
            ("max_discovery_calls", 16),
            ("max_action_attempts", 16),
            ("max_identical_actions", 4),
            ("max_identical_invalid_decisions", 4),
            ("max_retained_observations", 12),
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1 or value > maximum:
                raise ValueError(f"{field_name} must be between 1 and {maximum}.")


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
            raise ValueError("response_text must be non-empty.")

        if self.terminal is RuntimeTerminal.FAILED:
            if self.failure is None:
                raise ValueError("failed runtime result requires failure.")
        elif self.failure is not None:
            raise ValueError("non-failed runtime result must not contain failure.")

        if self.terminal is RuntimeTerminal.APPROVAL_REQUIRED:
            if self.pending_action is None or self.pending_authorization is None:
                raise ValueError(
                    "approval result requires pending action and authorization."
                )


class _RuntimeStop(RuntimeError):
    def __init__(self, reason: RuntimeFailureReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


_EVENT_SAFE_PROVIDER_GENERATION_FIELDS = {
    "finish_reason": "finish_reason",
    "usage_completion_tokens": "completion_count",
    "usage_prompt_tokens": "prompt_count",
    "stop_sequence_configured": "stop_sequence_configured",
    "content_bytes_before_sanitization": "content_bytes_before_sanitization",
    "content_bytes_after_sanitization": "content_bytes_after_sanitization",
    "provider_http_status": "provider_http_status",
}


@dataclass(frozen=True, slots=True)
class _CompletionRejection:
    """One parsed FINAL claim that lacks objective support."""

    reason: str
    claim: FinalClaim


@dataclass(frozen=True, slots=True)
class _CompletionObligation:
    """Bounded objective requirement retained after a rejected FINAL."""

    reason: str
    claim: FinalClaim
    required_capability_id: str | None
    requires_successful_evidence: bool
    requires_evidence_backed_claim: bool
    requires_fresh_evidence: bool


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
        event_store: AgentEventStore | None = None,
    ) -> None:
        if not isinstance(controller, AgentDecisionDriver):
            raise TypeError("controller must implement AgentDecisionDriver.")

        if not isinstance(discovery, CapabilityDiscovery):
            raise TypeError("discovery must be CapabilityDiscovery.")

        if not isinstance(authorizer, ActionAuthorizer):
            raise TypeError("authorizer must be ActionAuthorizer.")

        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError("capabilities must be CapabilityRegistry.")

        if not isinstance(executor, AuthorizedActionExecutor):
            raise TypeError("executor must implement AuthorizedActionExecutor.")

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
            raise ValueError("authorizer and discovery must share one target registry.")

        if authorizer.sources is not discovery.sources:
            raise ValueError("authorizer and discovery must share one source registry.")

        if config is not None and not isinstance(
            config,
            AgentRuntimeConfig,
        ):
            raise TypeError("config must be AgentRuntimeConfig or None.")

        self._controller = controller
        self._discovery = discovery
        self._authorizer = authorizer
        self._capabilities = capabilities
        self._executor = executor
        self._config = config or AgentRuntimeConfig()
        self._event_store = event_store or get_event_store()

    def run(
        self,
        request: str,
        *,
        permission_mode: PermissionMode,
        budget: AuthorityBudget | None = None,
        approval: ApprovalScope | None = None,
        request_id: str | None = None,
        chat_id: str | None = None,
        model_identity: Mapping[str, str] | None = None,
    ) -> AgentRuntimeResult:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be non-empty text.")

        if not isinstance(permission_mode, PermissionMode):
            raise TypeError("permission_mode must be PermissionMode.")

        if request_id is not None and (not isinstance(request_id, str) or not request_id):
            raise ValueError("request_id must be non-empty text or None.")
        if chat_id is not None and (not isinstance(chat_id, str) or not chat_id):
            raise ValueError("chat_id must be non-empty text or None.")
        if model_identity is not None and not isinstance(model_identity, Mapping):
            raise TypeError("model_identity must be a mapping or None.")

        correlation_id = request_id or uuid.uuid4().hex
        configured_provider = (
            model_identity.get("provider") if model_identity is not None else None
        )
        configured_model = (
            model_identity.get("model") if model_identity is not None else None
        )
        if not isinstance(configured_provider, str):
            configured_provider = None
        if not isinstance(configured_model, str):
            configured_model = None

        def emit(
            event_type: str,
            status: EventStatus,
            *,
            component: str = "canonical_runtime",
            duration_ms: float | None = None,
            error_code: str | None = None,
            capability_id: str | None = None,
            target_ref: str | None = None,
            source_ref: str | None = None,
            metadata: Mapping[str, object] | None = None,
        ) -> None:
            safe_metadata = dict(metadata or {})
            if configured_provider is not None:
                safe_metadata["configured_provider"] = configured_provider[:128]
            self._event_store.emit(
                AgentEvent(
                    occurred_at=datetime.now(timezone.utc),
                    request_id=correlation_id,
                    chat_id=chat_id,
                    component=component,
                    event_type=event_type,
                    status=status,
                    model=configured_model[:256] if configured_model else None,
                    capability_id=capability_id,
                    target_ref=target_ref,
                    source_ref=source_ref,
                    duration_ms=duration_ms,
                    error_code=error_code,
                    metadata=safe_metadata,
                )
            )

        current_budget = budget or AuthorityBudget()

        if not isinstance(current_budget, AuthorityBudget):
            raise TypeError("budget must be AuthorityBudget or None.")

        observations: list[AgentObservation] = []
        model_calls = 0
        discovery_calls = 0
        action_attempts = 0
        action_id = 0

        disclosed_capability: str | None = None
        disclosed_groups: set[str] = set()
        disclosed_capabilities: set[str] = set()
        last_action_fingerprint: str | None = None
        identical_action_count = 0
        last_invalid_fingerprint: str | None = None
        identical_invalid_count = 0
        last_completion_fingerprint: str | None = None
        identical_completion_count = 0
        completion_obligation: _CompletionObligation | None = None
        stage = _DecisionStage.FIRST

        def call_model(method, /, *args, **kwargs):
            nonlocal model_calls

            if model_calls >= self._config.max_model_calls:
                raise _RuntimeStop(RuntimeFailureReason.MODEL_CALL_LIMIT)

            model_calls += 1
            started_at = time.perf_counter()
            emit("model.started", EventStatus.STARTED, component="model")
            try:
                result = method(*args, **kwargs)
            except AgentModelError as exc:
                failure = exc.failures[-1] if exc.failures else None
                emit(
                    "model.failed",
                    EventStatus.FAILED,
                    component="model",
                    duration_ms=(time.perf_counter() - started_at) * 1000,
                    error_code=exc.reason.value,
                    metadata=(
                        {
                            "failure_provider": failure.provider,
                            "parse_diagnostics": _event_safe_parse_diagnostics(
                                failure.diagnostics,
                            ),
                        }
                        if failure is not None
                        else None
                    ),
                )
                raise
            except Exception:
                emit(
                    "model.failed",
                    EventStatus.FAILED,
                    component="model",
                    duration_ms=(time.perf_counter() - started_at) * 1000,
                    error_code="model_exception",
                )
                raise
            emit(
                "model.decision",
                EventStatus.SUCCEEDED,
                component="model",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                metadata={"decision_kind": result.decision.kind.value},
            )
            return result

        def retained() -> tuple[AgentObservation, ...]:
            return tuple(observations[-self._config.max_retained_observations :])

        try:
            decision_result = call_model(
                self._controller.decide_first,
                request,
                request_id=request_id,
            )

            while True:
                decision = decision_result.decision

                stage_error = _validate_stage_decision(
                    decision,
                    stage=stage,
                    available_groups=self._discovery.groups(),
                    disclosed_groups=disclosed_groups,
                    disclosed_capabilities=disclosed_capabilities,
                    selected_capability=disclosed_capability,
                )
                if stage_error is not None:
                    if decision.kind is DecisionKind.ACTION and decision.action is not None:
                        emit(
                            "action.rejected",
                            EventStatus.BLOCKED,
                            component="authority",
                            capability_id=decision.action.capability_id,
                            target_ref=decision.action.target_ref,
                            source_ref=decision.action.source_ref,
                            error_code=stage_error,
                        )
                    rejected_stage = stage
                    invalid_fingerprint = _decision_fingerprint(decision)
                    if invalid_fingerprint == last_invalid_fingerprint:
                        identical_invalid_count += 1
                    else:
                        last_invalid_fingerprint = invalid_fingerprint
                        identical_invalid_count = 1
                    if (
                        identical_invalid_count
                        > self._config.max_identical_invalid_decisions
                    ):
                        raise _RuntimeStop(RuntimeFailureReason.NO_PROGRESS)
                    disclosed_capability = None
                    stage = _DecisionStage.FEEDBACK
                    decision_result = call_model(
                        self._controller.decide_after_feedback,
                        request,
                        feedback={
                            "status": "invalid_decision",
                            "stage": rejected_stage.value,
                            "reason": stage_error,
                        },
                        request_id=request_id,
                    )
                    continue

                last_invalid_fingerprint = None
                identical_invalid_count = 0

                if decision.kind is DecisionKind.FINAL:
                    obligation_rejection = _completion_obligation_rejection(
                        completion_obligation,
                        claims=decision.claims,
                        observations=observations,
                    )
                    rejection = obligation_rejection or _final_claim_rejection(
                        decision.claims, observations
                    )
                    if rejection is not None:
                        if obligation_rejection is None:
                            completion_obligation = _completion_obligation_for(
                                rejection,
                                known_capability=(
                                    self._capabilities.get(
                                        rejection.claim.capability_id
                                    )
                                    is not None
                                ),
                            )
                        assert completion_obligation is not None
                        completion_fingerprint = _completion_rejection_fingerprint(
                            completion_obligation, observations
                        )
                        if completion_fingerprint == last_completion_fingerprint:
                            identical_completion_count += 1
                        else:
                            last_completion_fingerprint = completion_fingerprint
                            identical_completion_count = 1
                        observed_claim = _observed_claim_reference(
                            rejection.claim, observations
                        )
                        emit(
                            "completion.rejected",
                            EventStatus.BLOCKED,
                            component="completion",
                            capability_id=(
                                observed_claim.capability_id
                                if observed_claim is not None
                                else None
                            ),
                            target_ref=(
                                observed_claim.target_ref
                                if observed_claim is not None
                                else None
                            ),
                            source_ref=(
                                observed_claim.source_ref
                                if observed_claim is not None
                                else None
                            ),
                            error_code=rejection.reason,
                            metadata={
                                "claim_action_id": rejection.claim.action_id,
                                "claim_capability_id": rejection.claim.capability_id,
                                "claim_kind": rejection.claim.kind.value,
                            },
                        )
                        if (
                            identical_completion_count
                            > self._config.max_identical_invalid_decisions
                        ):
                            raise _RuntimeStop(RuntimeFailureReason.NO_PROGRESS)
                        disclosed_capability = None
                        stage = _DecisionStage.FEEDBACK
                        decision_result = call_model(
                            self._controller.decide_after_feedback,
                            request,
                            feedback=_completion_feedback(
                                rejection,
                                observations=retained(),
                                disclosed_groups=disclosed_groups,
                                final_allowed=_completion_obligation_final_allowed(
                                    completion_obligation, observations
                                ),
                            ),
                            request_id=request_id,
                        )
                        continue
                    completion_obligation = None
                    emit("model.final", EventStatus.SUCCEEDED, component="model")
                    return self._result(
                        RuntimeTerminal.FINAL,
                        decision.answer or "",
                        observations,
                        current_budget,
                        model_calls,
                        discovery_calls,
                        action_attempts,
                    )

                last_completion_fingerprint = None
                identical_completion_count = 0

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

                    if discovery_calls > self._config.max_discovery_calls:
                        raise _RuntimeStop(RuntimeFailureReason.DISCOVERY_LIMIT)

                    group = decision.category or ""
                    started_at = time.perf_counter()
                    emit(
                        "discovery.started",
                        EventStatus.STARTED,
                        component="discovery",
                        metadata={"group": group},
                    )
                    result = self._discovery.discover(group)

                    if result.status is DiscoveryStatus.DISCOVERED:
                        emit(
                            "discovery.completed",
                            EventStatus.SUCCEEDED,
                            component="discovery",
                            duration_ms=(time.perf_counter() - started_at) * 1000,
                            metadata={"group": group, "capability_count": len(result.summaries)},
                        )
                        if result.group is None:
                            raise _RuntimeStop(RuntimeFailureReason.CONTRACT_FAILURE)
                        disclosed_groups.add(result.group)
                        disclosed_capabilities.update(
                            _capability_ids_from_summaries(result.summaries)
                        )
                        stage = _DecisionStage.DISCOVERY
                        decision_result = call_model(
                            self._controller.decide_after_discovery,
                            request,
                            result=result,
                            additional_capability_groups=tuple(
                                candidate
                                for candidate in self._discovery.groups()
                                if candidate not in disclosed_groups
                            ),
                            request_id=request_id,
                        )
                    else:
                        emit(
                            "discovery.failed",
                            EventStatus.FAILED,
                            component="discovery",
                            duration_ms=(time.perf_counter() - started_at) * 1000,
                            error_code=result.status.value,
                            metadata={"group": group},
                        )
                        stage = _DecisionStage.FEEDBACK
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
                    raise _RuntimeStop(RuntimeFailureReason.CONTRACT_FAILURE)

                action = decision.action

                if action is None:
                    raise _RuntimeStop(RuntimeFailureReason.CONTRACT_FAILURE)

                emit(
                    "action.proposed",
                    EventStatus.INFO,
                    component="authority",
                    capability_id=action.capability_id,
                    target_ref=action.target_ref,
                    source_ref=action.source_ref,
                )

                if disclosed_capability != action.capability_id:
                    detail = self._discovery.selected_detail(action.capability_id)

                    if detail.status is not CapabilityDetailStatus.DISCLOSED:
                        emit(
                            "action.rejected",
                            EventStatus.BLOCKED,
                            component="authority",
                            capability_id=action.capability_id,
                            target_ref=action.target_ref,
                            source_ref=action.source_ref,
                            error_code=detail.status.value,
                        )
                        disclosed_capability = None
                        stage = _DecisionStage.FEEDBACK
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
                    stage = _DecisionStage.ACTION_DETAIL
                    continue

                # ACTION returned under the selected capability's closed schema.
                disclosed_capability = None
                action_attempts += 1

                if action_attempts > self._config.max_action_attempts:
                    raise _RuntimeStop(RuntimeFailureReason.ACTION_LIMIT)

                fingerprint = _action_fingerprint(action)

                if fingerprint == last_action_fingerprint:
                    identical_action_count += 1
                else:
                    last_action_fingerprint = fingerprint
                    identical_action_count = 1

                if identical_action_count > self._config.max_identical_actions:
                    raise _RuntimeStop(RuntimeFailureReason.NO_PROGRESS)

                authorization = self._authorizer.authorize(
                    action,
                    permission_mode=permission_mode,
                    budget=current_budget,
                    approval=approval,
                )

                action_id += 1

                if authorization.status is AuthorizationStatus.APPROVAL_REQUIRED:
                    emit(
                        "action.approval_requested",
                        EventStatus.BLOCKED,
                        component="authority",
                        capability_id=action.capability_id,
                        target_ref=action.target_ref,
                        source_ref=action.source_ref,
                        error_code=authorization.reason.value,
                    )
                    return AgentRuntimeResult(
                        terminal=RuntimeTerminal.APPROVAL_REQUIRED,
                        response_text=(
                            "Approval is required before this write action can execute."
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
                    emit(
                        "action.rejected",
                        EventStatus.BLOCKED,
                        component="authority",
                        capability_id=authorization.capability_id,
                        target_ref=authorization.target_ref,
                        source_ref=authorization.source_ref,
                        error_code=authorization.reason.value,
                    )
                    observation = authorization_observation(
                        action_id,
                        authorization,
                        provenance=_reference_rejection_provenance(
                            authorization.reason,
                            self._discovery.selected_detail(
                                authorization.capability_id
                            ).selected_capability_schema,
                        ),
                    )
                    observations.append(observation)
                    emit(
                        "evidence.created",
                        _event_status_for_observation(observation.status.value),
                        component="evidence",
                        capability_id=observation.capability_id,
                        target_ref=observation.target_ref,
                        source_ref=observation.source_ref,
                        error_code=observation.reason,
                    )

                    stage = _DecisionStage.OBSERVATION
                    decision_result = call_model(
                        self._controller.decide_after_observation,
                        request,
                        observations=retained(),
                        request_id=request_id,
                    )
                    continue

                capability = self._capabilities.get(authorization.capability_id)

                if capability is None:
                    raise _RuntimeStop(RuntimeFailureReason.CONTRACT_FAILURE)

                execution_request = AuthorizedExecutionRequest.from_authorization(
                    capability,
                    authorization,
                )

                if authorization.approval_id is not None:
                    emit(
                        "action.approved",
                        EventStatus.SUCCEEDED,
                        component="authority",
                        capability_id=authorization.capability_id,
                        target_ref=authorization.target_ref,
                        source_ref=authorization.source_ref,
                    )

                started_at = time.perf_counter()
                emit(
                    "tool.started",
                    EventStatus.STARTED,
                    component="executor",
                    capability_id=execution_request.capability_id,
                    target_ref=execution_request.target_ref,
                    source_ref=execution_request.source_ref,
                )
                try:
                    execution = self._executor.execute(execution_request)
                except Exception as exc:
                    emit(
                        "tool.failed",
                        EventStatus.FAILED,
                        component="executor",
                        duration_ms=(time.perf_counter() - started_at) * 1000,
                        capability_id=execution_request.capability_id,
                        target_ref=execution_request.target_ref,
                        source_ref=execution_request.source_ref,
                        error_code="executor_exception",
                    )
                    raise _RuntimeStop(RuntimeFailureReason.EXECUTOR_FAILURE) from exc

                if not isinstance(
                    execution,
                    AgentExecutionResult,
                ):
                    emit(
                        "tool.failed",
                        EventStatus.FAILED,
                        component="executor",
                        duration_ms=(time.perf_counter() - started_at) * 1000,
                        capability_id=execution_request.capability_id,
                        target_ref=execution_request.target_ref,
                        source_ref=execution_request.source_ref,
                        error_code="invalid_execution_result",
                    )
                    raise _RuntimeStop(RuntimeFailureReason.EXECUTOR_FAILURE)

                execution_duration = (time.perf_counter() - started_at) * 1000
                if execution.status is ExecutionStatus.SUCCESS:
                    emit(
                        "tool.completed",
                        EventStatus.SUCCEEDED,
                        component="executor",
                        duration_ms=execution_duration,
                        capability_id=execution_request.capability_id,
                        target_ref=execution_request.target_ref,
                        source_ref=execution_request.source_ref,
                    )
                else:
                    emit(
                        "tool.failed",
                        EventStatus.FAILED,
                        component="executor",
                        duration_ms=execution_duration,
                        capability_id=execution_request.capability_id,
                        target_ref=execution_request.target_ref,
                        source_ref=execution_request.source_ref,
                        error_code=execution.status.value,
                    )

                if execution.dispatched:
                    current_budget = current_budget.after_execution(
                        authorization.budget_cost
                    )

                observation = execution.to_observation(action_id, execution_request)
                observations.append(observation)
                emit(
                    "evidence.created",
                    _event_status_for_observation(observation.status.value),
                    component="evidence",
                    capability_id=observation.capability_id,
                    target_ref=observation.target_ref,
                    source_ref=observation.source_ref,
                    error_code=observation.reason if observation.status.value != "success" else None,
                )

                stage = _DecisionStage.OBSERVATION
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
            RuntimeFailureReason.MODEL_FAILURE: "The model could not produce a valid next step.",
            RuntimeFailureReason.MODEL_CALL_LIMIT: "The agent stopped after reaching its model-call limit.",
            RuntimeFailureReason.DISCOVERY_LIMIT: "The agent stopped after reaching its discovery limit.",
            RuntimeFailureReason.ACTION_LIMIT: "The agent stopped after reaching its action limit.",
            RuntimeFailureReason.NO_PROGRESS: "The agent stopped because it was not making progress.",
            RuntimeFailureReason.CONTRACT_FAILURE: "The agent stopped because a runtime contract was invalid.",
            RuntimeFailureReason.EXECUTOR_FAILURE: "The agent stopped because execution could not be completed.",
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


def _event_safe_parse_diagnostics(
    diagnostics: Mapping[str, object],
) -> dict[str, object]:
    """Project provider diagnostics into names accepted by event hardening."""

    projected = dict(diagnostics)
    provider_generation = diagnostics.get("provider_generation")
    if not isinstance(provider_generation, Mapping):
        return projected

    safe_generation: dict[str, object] = {}
    for internal_name, event_name in _EVENT_SAFE_PROVIDER_GENERATION_FIELDS.items():
        if internal_name in provider_generation:
            safe_generation[event_name] = provider_generation[internal_name]
    projected["provider_generation"] = safe_generation
    return projected


def _action_fingerprint(action: AgentAction) -> str:
    payload = action.to_wire()
    payload.pop("activity_text", None)

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _event_status_for_observation(status: str) -> EventStatus:
    """Project normalized evidence status without exposing its payload."""
    if status == "success":
        return EventStatus.SUCCEEDED
    if status == "blocked":
        return EventStatus.BLOCKED
    return EventStatus.FAILED


def _decision_fingerprint(decision: AgentDecision) -> str:
    return json.dumps(
        decision.to_wire(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _capability_ids_from_summaries(
    summaries: Sequence[Mapping[str, object]],
) -> set[str]:
    identifiers: set[str] = set()
    for summary in summaries:
        capability_id = summary.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            raise ValueError("Discovery summary contains invalid capability_id.")
        identifiers.add(capability_id)
    return identifiers


def _validate_stage_decision(
    decision: AgentDecision,
    *,
    stage: _DecisionStage,
    available_groups: Sequence[str],
    disclosed_groups: set[str],
    disclosed_capabilities: set[str],
    selected_capability: str | None,
) -> str | None:
    """Validate actual progressive-disclosure state after provider parsing.

    Provider JSON schema is deliberately only a generation aid.  This check
    uses current harness state rather than registry reachability, so a model
    cannot turn a known-but-undisclosed capability into authority.
    """
    allowed_by_stage = {
        _DecisionStage.FIRST: {
            DecisionKind.FINAL,
            DecisionKind.DISCOVER,
            DecisionKind.CLARIFY,
            DecisionKind.REFUSE,
        },
        _DecisionStage.DISCOVERY: {
            DecisionKind.FINAL,
            DecisionKind.DISCOVER,
            DecisionKind.ACTION,
            DecisionKind.CLARIFY,
            DecisionKind.REFUSE,
        },
        _DecisionStage.ACTION_DETAIL: {DecisionKind.ACTION},
        _DecisionStage.OBSERVATION: {
            DecisionKind.FINAL,
            DecisionKind.DISCOVER,
            DecisionKind.ACTION,
            DecisionKind.CLARIFY,
            DecisionKind.REFUSE,
        },
        _DecisionStage.FEEDBACK: {
            DecisionKind.FINAL,
            DecisionKind.DISCOVER,
            DecisionKind.ACTION,
            DecisionKind.CLARIFY,
            DecisionKind.REFUSE,
        },
    }
    if decision.kind not in allowed_by_stage[stage]:
        return f"{decision.kind.value}_not_allowed_in_{stage.value}"

    if decision.kind is DecisionKind.DISCOVER:
        category = decision.category
        if category not in available_groups:
            return "undisclosed_or_unknown_capability_group"
        if category in disclosed_groups:
            return "capability_group_already_disclosed"
        return None

    if decision.kind is not DecisionKind.ACTION:
        return None

    action = decision.action
    if action is None:  # defensive: AgentDecision already enforces this
        return "missing_action"
    if stage is _DecisionStage.ACTION_DETAIL:
        if action.capability_id != selected_capability:
            return "action_does_not_match_selected_capability"
        return None
    if action.capability_id not in disclosed_capabilities:
        return "capability_not_disclosed_in_current_turn"
    return None


def _final_claim_rejection(
    claims: Sequence[FinalClaim], observations: Sequence[AgentObservation]
) -> _CompletionRejection | None:
    """Validate structured FINAL claims without interpreting answer language."""
    by_id = {observation.action_id: observation for observation in observations}
    for claim in claims:
        observation = by_id.get(claim.action_id)
        if observation is None:
            return _CompletionRejection("evidence_missing", claim)
        if observation.status.value != "success":
            return _CompletionRejection("evidence_not_successful", claim)
        if observation.capability_id != claim.capability_id:
            return _CompletionRejection("capability_mismatch", claim)
        if (
            claim.target_ref != observation.target_ref
            or claim.source_ref != observation.source_ref
        ):
            return _CompletionRejection("reference_mismatch", claim)
        if claim.require_fresh and not isinstance(
            observation.provenance.get("observed_at"), str
        ):
            return _CompletionRejection("freshness_not_supported", claim)
        if (
            claim.kind is FinalClaimKind.DETERMINISTIC_RESULT
            and claim.result not in observation.facts
        ):
            return _CompletionRejection("deterministic_result_mismatch", claim)
    return None


def _completion_obligation_for(
    rejection: _CompletionRejection,
    *,
    known_capability: bool,
) -> _CompletionObligation:
    """Derive an objective retry requirement without interpreting answer prose."""
    reason = rejection.reason
    requires_successful_evidence = reason in {
        "evidence_missing",
        "evidence_not_successful",
        "freshness_not_supported",
    }
    return _CompletionObligation(
        reason=reason,
        claim=rejection.claim,
        required_capability_id=(
            rejection.claim.capability_id if known_capability else None
        ),
        requires_successful_evidence=requires_successful_evidence,
        requires_evidence_backed_claim=reason
        in {
            "capability_mismatch",
            "reference_mismatch",
            "deterministic_result_mismatch",
            "freshness_not_supported",
        },
        requires_fresh_evidence=reason == "freshness_not_supported",
    )


def _completion_obligation_rejection(
    obligation: _CompletionObligation | None,
    *,
    claims: Sequence[FinalClaim],
    observations: Sequence[AgentObservation],
) -> _CompletionRejection | None:
    """Prevent a retry from erasing a previously rejected objective claim."""
    if obligation is None:
        return None
    if not _completion_obligation_final_allowed(obligation, observations):
        return _CompletionRejection("completion_requirement_unresolved", obligation.claim)
    if obligation.requires_evidence_backed_claim and not claims:
        return _CompletionRejection("completion_requirement_unresolved", obligation.claim)
    return None


def _completion_obligation_final_allowed(
    obligation: _CompletionObligation,
    observations: Sequence[AgentObservation],
) -> bool:
    """Return whether evidence prerequisites permit FINAL in recovery feedback."""
    if not obligation.requires_successful_evidence:
        return True
    return any(
        observation.status.value == "success"
        and (
            obligation.required_capability_id is None
            or observation.capability_id == obligation.required_capability_id
        )
        and (
            not obligation.requires_fresh_evidence
            or isinstance(observation.provenance.get("observed_at"), str)
        )
        for observation in observations
    )


def _observed_claim_reference(
    claim: FinalClaim,
    observations: Sequence[AgentObservation],
) -> AgentObservation | None:
    """Project only references grounded by runtime observations into events."""
    return next(
        (
            observation
            for observation in observations
            if observation.action_id == claim.action_id
        ),
        None,
    )


def _completion_feedback(
    rejection: _CompletionRejection,
    *,
    observations: Sequence[AgentObservation],
    disclosed_groups: set[str],
    final_allowed: bool,
) -> dict[str, object]:
    """Return bounded machine-readable feedback for a recoverable FINAL."""
    claim = rejection.claim
    return {
        "status": "completion_rejected",
        "reason": rejection.reason,
        "final_allowed": final_allowed,
        "claim": {
            "action_id": claim.action_id,
            "capability_id": claim.capability_id,
            "target_ref": claim.target_ref,
            "source_ref": claim.source_ref,
            "kind": claim.kind.value,
        },
        "disclosed_groups": sorted(disclosed_groups),
        "evidence": [
            {
                "action_id": observation.action_id,
                "capability_id": observation.capability_id,
                "status": observation.status.value,
                "target_ref": observation.target_ref,
                "source_ref": observation.source_ref,
            }
            for observation in observations
        ],
    }


def _reference_rejection_provenance(
    reason: AuthorizationReason,
    selected_schema: Mapping[str, object] | None,
) -> dict[str, object]:
    """Retain selected reference authority after a rejected ACTION_DETAIL call."""
    if reason not in {
        AuthorizationReason.TARGET_NOT_ALLOWED,
        AuthorizationReason.SOURCE_NOT_ALLOWED,
    } or not isinstance(selected_schema, Mapping):
        return {}

    constraints: dict[str, object] = {}
    for field_name in ("target_ref", "source_ref"):
        contract = selected_schema.get(field_name)
        if isinstance(contract, Mapping):
            constraints[field_name] = dict(contract)
    return {"reference_constraints": constraints}


def _completion_rejection_fingerprint(
    obligation: _CompletionObligation,
    observations: Sequence[AgentObservation],
) -> str:
    """Fingerprint safe claim/evidence identifiers, never answer prose or facts."""
    claim = obligation.claim
    return json.dumps(
        {
            "obligation": {
                "reason": obligation.reason,
                "required_capability_id": obligation.required_capability_id,
                "requires_successful_evidence": obligation.requires_successful_evidence,
                "requires_evidence_backed_claim": (
                    obligation.requires_evidence_backed_claim
                ),
                "requires_fresh_evidence": obligation.requires_fresh_evidence,
            },
            "claim": {
                "action_id": claim.action_id,
                "capability_id": claim.capability_id,
                "target_ref": claim.target_ref,
                "source_ref": claim.source_ref,
                "kind": claim.kind.value,
                "require_fresh": claim.require_fresh,
            },
            "evidence": [
                {
                    "action_id": observation.action_id,
                    "capability_id": observation.capability_id,
                    "status": observation.status.value,
                    "target_ref": observation.target_ref,
                    "source_ref": observation.source_ref,
                }
                for observation in observations
            ],
        },
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
