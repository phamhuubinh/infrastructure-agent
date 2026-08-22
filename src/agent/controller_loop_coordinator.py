"""Bounded Agent v2 reason-act-observe controller loop.

This coordinator is deliberately separate from the legacy semantic loop and
has no runtime-factory wiring.  It composes the v2 controller, discovery,
validation, execution, and observation contracts without granting a model
execution authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum

from src.agent.completion_check import CompletionCheck
from src.agent.controller_contracts import (
    AgentDecision,
    AgentDecisionKind,
    AgentObservation,
    AgentObservationStatus,
    AgentRunState,
    ControllerCallStage,
)
from src.agent.controller_session_context import (
    ContextManagementStatus,
    ControllerSessionContext,
)
from src.agent.conversation_store import ConversationStoreProtocol
from src.model.controller_adapter import ControllerAdapter, ControllerAdapterError
from src.model.output_sanitizer import sanitize_api_response
from src.model.protocol.controller_prompt import (
    ControllerContinuationInput,
    ControllerPromptContext,
    build_controller_prompt,
)
from src.pipeline.agent_action_executor import AgentActionExecutor
from src.pipeline.agent_action_validator import (
    AgentActionToolBudget,
    AgentActionValidationStatus,
    AgentActionValidator,
)
from src.pipeline.agent_observation_serializer import (
    retain_agent_observations,
    serialize_control_feedback,
    serialize_discovery_observation,
    serialize_execution_observation,
    serialize_validation_failure,
)
from src.pipeline.controller_capability_discovery import (
    CapabilityDetailStatus,
    CapabilityDiscoveryStatus,
    ControllerCapabilityDiscovery,
)
from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.pipeline.input_context_budget import InputContextBudgetError


class AgentControllerLoopState(str, Enum):
    SAFETY_STOP = "safety_stop"
    MANAGE_CONTEXT = "manage_context"
    DECIDE = "decide"
    DISCOVER = "discover"
    DISCLOSE_ACTION = "disclose_action"
    VALIDATE_ACTION = "validate_action"
    EXECUTE_ACTION = "execute_action"
    OBSERVE = "observe"
    CHECK_FINAL = "check_final"
    DONE = "done"
    FAIL = "fail"


class AgentControllerLoopRecordStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentControllerLoopFailure(str, Enum):
    PROVIDER_FAILURE = "provider_failure"
    CONTROLLER_ROUND_LIMIT = "controller_round_limit"
    MODEL_CALL_LIMIT = "model_call_limit"
    DISCOVERY_LIMIT = "discovery_limit"
    ACTION_BUDGET_EXHAUSTED = "action_budget_exhausted"
    CONTROLLER_INPUT_BUDGET_EXHAUSTED = "controller_input_budget_exhausted"
    STATE_LIMIT = "state_limit"
    FINALIZATION_FAILED = "finalization_failed"
    COMPLETION_FEEDBACK_LIMIT = "completion_feedback_limit"
    CONTRACT_FAILURE = "contract_failure"


@dataclass(frozen=True, slots=True)
class AgentControllerLoopStateRecord:
    """One inspectable transition outcome, with no model or evidence text."""

    state: AgentControllerLoopState
    status: AgentControllerLoopRecordStatus
    reason_code: str

    def to_trace_dict(self) -> dict[str, str]:
        return {
            "state": self.state.value,
            "status": self.status.value,
            "reason": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class AgentControllerPromptRecord:
    """Safe context-budget metadata for one completed controller call."""

    call_stage: ControllerCallStage
    input_budget_class: str
    input_budget_max_chars: int
    actual_input_chars: int
    estimated_input_tokens: int
    optional_included: tuple[str, ...]
    optional_dropped: tuple[str, ...]

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "call_stage": self.call_stage.value,
            "input_budget_class": self.input_budget_class,
            "input_budget_max_chars": self.input_budget_max_chars,
            "actual_input_chars": self.actual_input_chars,
            "estimated_input_tokens": self.estimated_input_tokens,
            "optional_included": list(self.optional_included),
            "optional_dropped": list(self.optional_dropped),
        }


@dataclass(frozen=True, slots=True)
class AgentControllerLoopConfig:
    max_controller_rounds: int = 8
    max_model_calls: int = 8
    max_discovery_calls: int = 3
    max_actions: int = 4
    max_tools: int = 4
    max_total_controller_input_tokens: int = 12_000
    max_state_transitions: int = 48
    max_completion_feedback: int = 3

    def __post_init__(self) -> None:
        _bounded_int("max_controller_rounds", self.max_controller_rounds, 1, 32)
        _bounded_int("max_model_calls", self.max_model_calls, 1, 32)
        _bounded_int("max_discovery_calls", self.max_discovery_calls, 0, 16)
        _bounded_int("max_actions", self.max_actions, 0, 16)
        _bounded_int("max_tools", self.max_tools, 0, 16)
        _bounded_int(
            "max_total_controller_input_tokens",
            self.max_total_controller_input_tokens,
            1,
            100_000,
        )
        _bounded_int("max_state_transitions", self.max_state_transitions, 2, 128)
        _bounded_int("max_completion_feedback", self.max_completion_feedback, 0, 8)


FinalBoundary = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class AgentControllerLoopResult:
    terminal_state: AgentControllerLoopState
    response_text: str
    run_state: AgentRunState
    records: tuple[AgentControllerLoopStateRecord, ...]
    failure: AgentControllerLoopFailure | None
    discovery_call_count: int
    accumulated_controller_input_tokens: int
    action_budget: AgentActionToolBudget
    completion_feedback_count: int
    controller_prompt_metadata: tuple[AgentControllerPromptRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.terminal_state not in {
            AgentControllerLoopState.DONE,
            AgentControllerLoopState.FAIL,
        }:
            raise ValueError("Controller loop result must be terminal.")
        if not isinstance(self.response_text, str) or not self.response_text.strip():
            raise ValueError("Controller loop result requires one non-empty response.")
        if not self.run_state.terminal:
            raise ValueError(
                "Terminal controller loop result requires terminal run state."
            )
        if (
            self.discovery_call_count < 0
            or self.accumulated_controller_input_tokens < 0
        ):
            raise ValueError("Controller counters must be non-negative.")

    @property
    def succeeded(self) -> bool:
        return self.terminal_state is AgentControllerLoopState.DONE

    @property
    def final_response_count(self) -> int:
        return 1

    def to_trace_dict(self) -> dict[str, object]:
        """Return safe loop metadata only; user/model prose is intentionally absent."""

        return {
            "terminal_state": self.terminal_state.value,
            "succeeded": self.succeeded,
            "state_history": [record.state.value for record in self.records],
            "states": [record.to_trace_dict() for record in self.records],
            "failure": self.failure.value if self.failure is not None else None,
            "discovery_call_count": self.discovery_call_count,
            "accumulated_controller_input_tokens": self.accumulated_controller_input_tokens,
            "action_budget": {
                "max_actions": self.action_budget.max_actions,
                "actions_used": self.action_budget.actions_used,
                "max_tools": self.action_budget.max_tools,
                "tools_used": self.action_budget.tools_used,
            },
            "completion_feedback_count": self.completion_feedback_count,
            "controller_prompt_metadata": [
                item.to_trace_dict() for item in self.controller_prompt_metadata
            ],
            "run_state": self.run_state.to_trace_dict(),
            "final_response_count": 1,
        }


class AgentControllerLoopCoordinator:
    """Run one finite Agent v2 controller loop without automatic retries."""

    def __init__(
        self,
        *,
        controller: ControllerAdapter,
        discovery: ControllerCapabilityDiscovery,
        validator: AgentActionValidator,
        executor: AgentActionExecutor,
        final_boundary: FinalBoundary | None = None,
        completion_check: CompletionCheck | None = None,
        config: AgentControllerLoopConfig | None = None,
    ) -> None:
        if not isinstance(controller, ControllerAdapter):
            raise TypeError("controller must be a ControllerAdapter.")
        if not isinstance(discovery, ControllerCapabilityDiscovery):
            raise TypeError("discovery must be a ControllerCapabilityDiscovery.")
        if not isinstance(validator, AgentActionValidator):
            raise TypeError("validator must be an AgentActionValidator.")
        if not isinstance(executor, AgentActionExecutor):
            raise TypeError("executor must be an AgentActionExecutor.")
        if final_boundary is not None and not callable(final_boundary):
            raise TypeError("final_boundary must be callable or None.")
        if config is not None and not isinstance(config, AgentControllerLoopConfig):
            raise TypeError("config must be AgentControllerLoopConfig or None.")
        if completion_check is not None and not isinstance(
            completion_check, CompletionCheck
        ):
            raise TypeError("completion_check must be CompletionCheck or None.")
        self._controller = controller
        self._discovery = discovery
        self._validator = validator
        self._executor = executor
        self._final_boundary = final_boundary or _pass_final_answer
        self._completion_check = completion_check or CompletionCheck()
        self._config = config or AgentControllerLoopConfig()

    def run(
        self,
        raw_request: str,
        *,
        hard_constraints: HardRequestConstraints,
        context: ControllerPromptContext | None = None,
        session_store: ConversationStoreProtocol | None = None,
        request_id: str | None = None,
    ) -> AgentControllerLoopResult:
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("raw_request must be non-empty text.")
        if not isinstance(hard_constraints, HardRequestConstraints):
            raise TypeError("hard_constraints must be HardRequestConstraints.")
        if context is not None and not isinstance(context, ControllerPromptContext):
            raise TypeError("context must be ControllerPromptContext or None.")
        if request_id is not None and (
            not isinstance(request_id, str) or not request_id
        ):
            raise ValueError("request_id must be non-empty text or None.")

        session_context: ControllerSessionContext | None = None
        controller_context = context
        state = AgentControllerLoopState.DECIDE
        records: list[AgentControllerLoopStateRecord] = []
        run_state = AgentRunState(
            raw_request=raw_request,
            hard_constraint_snapshot=hard_constraints.to_dict(),
        )
        action_budget = AgentActionToolBudget(
            max_actions=self._config.max_actions,
            max_tools=self._config.max_tools,
        )
        discovery_calls = 0
        input_tokens = 0
        observation_sequence = 0
        pending_summaries: tuple[Mapping[str, object], ...] = ()
        active_selected_schema: Mapping[str, object] | None = None
        pending_observation: AgentObservation | None = None
        pending_identity: tuple[str | None, str | None, str | None] = (None, None, None)
        decision: AgentDecision | None = None
        validation = None
        effective_constraints = hard_constraints
        completion_feedback_count = 0
        action_schema: Mapping[str, object] | None = None
        call_stage = ControllerCallStage.FIRST_DECISION
        controller_prompt_metadata: list[AgentControllerPromptRecord] = []

        def record(
            record_state: AgentControllerLoopState,
            status: AgentControllerLoopRecordStatus,
            reason_code: str,
        ) -> None:
            records.append(
                AgentControllerLoopStateRecord(record_state, status, reason_code)
            )

        def next_observation(
            observation: AgentObservation,
            *,
            capability_id: str | None = None,
            target_id: str | None = None,
            source_id: str | None = None,
        ) -> None:
            nonlocal pending_observation, pending_identity
            pending_observation = observation
            pending_identity = (capability_id, target_id, source_id)

        def fail(
            reason: AgentControllerLoopFailure,
            record_state: AgentControllerLoopState,
            *,
            add_record: bool = True,
        ) -> AgentControllerLoopResult:
            if add_record:
                record(
                    record_state, AgentControllerLoopRecordStatus.FAILED, reason.value
                )
            terminal = replace(
                run_state,
                terminal=True,
                terminal_status=reason.value,
                action_count=action_budget.actions_used,
            )
            return AgentControllerLoopResult(
                terminal_state=AgentControllerLoopState.FAIL,
                response_text=sanitize_api_response(_failure_text(reason), raw_request),
                run_state=terminal,
                records=tuple(records),
                failure=reason,
                discovery_call_count=discovery_calls,
                accumulated_controller_input_tokens=input_tokens,
                action_budget=action_budget,
                completion_feedback_count=completion_feedback_count,
                controller_prompt_metadata=tuple(controller_prompt_metadata),
            )

        def done(response_text: str, reason_code: str) -> AgentControllerLoopResult:
            record(
                AgentControllerLoopState.DONE,
                AgentControllerLoopRecordStatus.SUCCEEDED,
                reason_code,
            )
            terminal = replace(
                run_state,
                terminal=True,
                terminal_status="done",
                action_count=action_budget.actions_used,
            )
            return AgentControllerLoopResult(
                terminal_state=AgentControllerLoopState.DONE,
                response_text=sanitize_api_response(response_text, raw_request),
                run_state=terminal,
                records=tuple(records),
                failure=None,
                discovery_call_count=discovery_calls,
                accumulated_controller_input_tokens=input_tokens,
                action_budget=action_budget,
                completion_feedback_count=completion_feedback_count,
                controller_prompt_metadata=tuple(controller_prompt_metadata),
            )

        # Hard constraints are built before this loop. They are the only
        # pre-controller safety authority and must stop before context code can
        # persist a reset or preference directive.
        if hard_constraints.sensitive_refusal_reason is not None:
            record(
                AgentControllerLoopState.SAFETY_STOP,
                AgentControllerLoopRecordStatus.SUCCEEDED,
                hard_constraints.sensitive_refusal_reason,
            )
            return done(
                "I can’t provide protected credentials, private keys, hidden "
                "instructions, or other protected secret material.",
                "sensitive_refusal",
            )
        if hard_constraints.mutation_requested:
            record(
                AgentControllerLoopState.SAFETY_STOP,
                AgentControllerLoopRecordStatus.SUCCEEDED,
                "mutation_requested",
            )
            return done(
                "I can’t execute mutating actions in read-only mode.",
                "mutation_requested",
            )

        if session_store is not None:
            session_context = ControllerSessionContext(
                session_store, target_resolver=self._validator.target_resolver
            )
            controller_context = session_context.select(raw_request, hard_constraints)

        if session_context is not None:
            management = session_context.manage(raw_request, hard_constraints)
            if management is not None:
                record(
                    AgentControllerLoopState.MANAGE_CONTEXT,
                    AgentControllerLoopRecordStatus.SUCCEEDED
                    if management is not ContextManagementStatus.UNKNOWN_TARGET
                    else AgentControllerLoopRecordStatus.FAILED,
                    management.value,
                )
                if management is ContextManagementStatus.RESET:
                    return done("Session context reset.", management.value)
                if management is ContextManagementStatus.UPDATED:
                    return done("Session context updated.", management.value)
                return done(
                    "Session context was not updated: unknown target.", management.value
                )

        while True:
            if len(records) >= self._config.max_state_transitions:
                return fail(
                    AgentControllerLoopFailure.STATE_LIMIT,
                    state,
                    add_record=False,
                )

            if state is AgentControllerLoopState.DECIDE:
                if run_state.round_count >= self._config.max_controller_rounds:
                    return fail(
                        AgentControllerLoopFailure.CONTROLLER_ROUND_LIMIT, state
                    )
                if run_state.model_call_count >= self._config.max_model_calls:
                    return fail(AgentControllerLoopFailure.MODEL_CALL_LIMIT, state)
                continuation = None
                if run_state.model_call_count:
                    continuation = ControllerContinuationInput(
                        run_state=run_state,
                        capability_summaries=pending_summaries,
                        selected_capability_schema=active_selected_schema,
                        session_context=controller_context,
                    )
                try:
                    preview = build_controller_prompt(
                        raw_request,
                        hard_constraints=hard_constraints,
                        context=controller_context if continuation is None else None,
                        continuation=continuation,
                        call_stage=call_stage,
                    )
                except InputContextBudgetError:
                    return fail(
                        AgentControllerLoopFailure.CONTROLLER_INPUT_BUDGET_EXHAUSTED,
                        state,
                    )
                except (TypeError, ValueError):
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                if (
                    input_tokens + preview.estimated_input_tokens
                    > self._config.max_total_controller_input_tokens
                ):
                    return fail(
                        AgentControllerLoopFailure.CONTROLLER_INPUT_BUDGET_EXHAUSTED,
                        state,
                    )
                input_tokens += preview.estimated_input_tokens
                run_state = replace(
                    run_state,
                    round_count=run_state.round_count + 1,
                    model_call_count=run_state.model_call_count + 1,
                )
                schema_for_decision = active_selected_schema
                # Both disclosure forms are one-turn input only.
                active_selected_schema = None
                pending_summaries = ()
                try:
                    decision_result = self._controller.decide(
                        raw_request,
                        hard_constraints=hard_constraints,
                        context=controller_context if continuation is None else None,
                        continuation=continuation,
                        call_stage=call_stage,
                        request_id=request_id,
                    )
                    decision = decision_result.decision
                except ControllerAdapterError:
                    return fail(AgentControllerLoopFailure.PROVIDER_FAILURE, state)
                except (TypeError, ValueError):
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                except Exception:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                if not isinstance(decision, AgentDecision):
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                controller_prompt_metadata.append(
                    AgentControllerPromptRecord(
                        call_stage=decision_result.call_stage,
                        input_budget_class=decision_result.input_budget_class,
                        input_budget_max_chars=decision_result.input_budget_max_chars,
                        actual_input_chars=decision_result.actual_input_chars,
                        estimated_input_tokens=decision_result.estimated_input_tokens,
                        optional_included=decision_result.optional_included,
                        optional_dropped=decision_result.optional_dropped,
                    )
                )
                # A disclosure stage is consumed by this call.  Any later
                # feedback-only turn is an observation continuation unless a
                # new discovery/schema disclosure below explicitly replaces it.
                call_stage = ControllerCallStage.OBSERVATION_CONTINUATION
                record(
                    state,
                    AgentControllerLoopRecordStatus.SUCCEEDED,
                    decision.kind.value,
                )
                if decision.kind is AgentDecisionKind.FINAL:
                    state = AgentControllerLoopState.CHECK_FINAL
                elif decision.kind is AgentDecisionKind.CLARIFY:
                    return done(
                        decision.clarification_question
                        or "Please clarify your request.",
                        "clarify",
                    )
                elif decision.kind is AgentDecisionKind.REFUSE:
                    return done(
                        decision.refusal_reason
                        or "Unable to safely complete the request.",
                        "refuse",
                    )
                elif decision.kind is AgentDecisionKind.DISCOVER:
                    state = AgentControllerLoopState.DISCOVER
                elif decision.kind is AgentDecisionKind.ACTION:
                    if schema_for_decision is None:
                        state = AgentControllerLoopState.DISCLOSE_ACTION
                    elif (
                        decision.action is None
                        or decision.action.capability_id
                        != schema_for_decision.get("capability_id")
                    ):
                        observation_sequence += 1
                        next_observation(
                            serialize_control_feedback(
                                observation_sequence,
                                status=AgentObservationStatus.INVALID_ACTION,
                                reason_code="selected_capability_mismatch",
                                capability_id=decision.action.capability_id,
                                recoverable=True,
                            )
                        )
                        state = AgentControllerLoopState.OBSERVE
                    else:
                        action_schema = schema_for_decision
                        state = AgentControllerLoopState.VALIDATE_ACTION
                else:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                continue

            if state is AgentControllerLoopState.DISCOVER:
                if discovery_calls >= self._config.max_discovery_calls:
                    return fail(AgentControllerLoopFailure.DISCOVERY_LIMIT, state)
                if decision is None or decision.category is None:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                discovery_calls += 1
                try:
                    discovery_result = self._discovery.discover(
                        decision.category,
                        (
                            session_context.discovery_constraints(hard_constraints)
                            if session_context is not None
                            else hard_constraints
                        ),
                    )
                    observation_sequence += 1
                    next_observation(
                        serialize_discovery_observation(
                            observation_sequence,
                            discovery_result,
                            category=decision.category,
                        )
                    )
                except (TypeError, ValueError):
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                if discovery_result.status is CapabilityDiscoveryStatus.DISCOVERED:
                    pending_summaries = tuple(discovery_result.summaries)
                    categories = _append_unique(
                        run_state.disclosed_capability_categories, decision.category
                    )
                    run_state = replace(
                        run_state, disclosed_capability_categories=categories
                    )
                    call_stage = ControllerCallStage.DISCOVERY_CONTINUATION
                record(
                    state,
                    AgentControllerLoopRecordStatus.SUCCEEDED,
                    discovery_result.status.value,
                )
                state = AgentControllerLoopState.OBSERVE
                continue

            if state is AgentControllerLoopState.DISCLOSE_ACTION:
                if decision is None or decision.action is None:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                try:
                    detail = self._discovery.selected_detail(
                        decision.action.capability_id,
                        (
                            session_context.discovery_constraints(hard_constraints)
                            if session_context is not None
                            else hard_constraints
                        ),
                    )
                except (TypeError, ValueError):
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                if detail.status is CapabilityDetailStatus.DISCLOSED:
                    if detail.selected_capability_schema is None:
                        return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                    active_selected_schema = detail.selected_capability_schema
                    call_stage = ControllerCallStage.ACTION_CONTINUATION
                    run_state = replace(
                        run_state,
                        disclosed_capability_detail_ids=_append_unique(
                            run_state.disclosed_capability_detail_ids,
                            decision.action.capability_id,
                        ),
                    )
                    record(
                        state,
                        AgentControllerLoopRecordStatus.SUCCEEDED,
                        "schema_disclosed",
                    )
                    state = AgentControllerLoopState.DECIDE
                    continue
                observation_sequence += 1
                if detail.status is CapabilityDetailStatus.UNKNOWN_CAPABILITY:
                    observation = serialize_control_feedback(
                        observation_sequence,
                        status=AgentObservationStatus.INVALID_ACTION,
                        reason_code="unknown_capability",
                        capability_id=decision.action.capability_id,
                        recoverable=True,
                    )
                elif detail.status is CapabilityDetailStatus.UNAVAILABLE_CAPABILITY:
                    observation = serialize_control_feedback(
                        observation_sequence,
                        status=AgentObservationStatus.UNAVAILABLE,
                        reason_code="unavailable_capability",
                        capability_id=decision.action.capability_id,
                        recoverable=True,
                    )
                else:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                next_observation(observation)
                record(
                    state, AgentControllerLoopRecordStatus.FAILED, detail.status.value
                )
                state = AgentControllerLoopState.OBSERVE
                continue

            if state is AgentControllerLoopState.VALIDATE_ACTION:
                if decision is None or decision.action is None:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                if not action_budget.permits_one_execution():
                    return fail(
                        AgentControllerLoopFailure.ACTION_BUDGET_EXHAUSTED, state
                    )
                try:
                    effective_constraints = (
                        session_context.action_constraints(
                            hard_constraints, action_schema
                        )
                        if session_context is not None
                        else hard_constraints
                    )
                    validation = self._validator.validate(
                        decision.action, effective_constraints, action_budget
                    )
                except (TypeError, ValueError):
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                if validation.status is not AgentActionValidationStatus.VALID:
                    if session_context is not None:
                        session_context.record_validation(
                            validation, hard_constraints, effective_constraints
                        )
                    observation_sequence += 1
                    next_observation(
                        serialize_validation_failure(observation_sequence, validation),
                        capability_id=validation.capability_id,
                        target_id=validation.target_id,
                        source_id=validation.source_id,
                    )
                    record(
                        state,
                        AgentControllerLoopRecordStatus.FAILED,
                        validation.reason.value,
                    )
                    state = AgentControllerLoopState.OBSERVE
                else:
                    if session_context is not None:
                        session_context.record_validation(
                            validation, hard_constraints, effective_constraints
                        )
                    record(
                        state,
                        AgentControllerLoopRecordStatus.SUCCEEDED,
                        validation.reason.value,
                    )
                    state = AgentControllerLoopState.EXECUTE_ACTION
                continue

            if state is AgentControllerLoopState.EXECUTE_ACTION:
                if validation is None:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                try:
                    execution = self._executor.execute(
                        validation,
                        action_budget,
                        raw_request=raw_request,
                        hard_constraints=effective_constraints,
                    )
                    action_budget = execution.budget
                    run_state = replace(
                        run_state, action_count=action_budget.actions_used
                    )
                    observation_sequence += 1
                    next_observation(
                        serialize_execution_observation(
                            observation_sequence, execution
                        ),
                        capability_id=execution.capability_id,
                        target_id=execution.target_id,
                        source_id=execution.source_id,
                    )
                except (TypeError, ValueError):
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                record(
                    state,
                    AgentControllerLoopRecordStatus.SUCCEEDED,
                    execution.status.value,
                )
                state = AgentControllerLoopState.OBSERVE
                continue

            if state is AgentControllerLoopState.OBSERVE:
                if pending_observation is None:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                capability_id, target_id, source_id = pending_identity
                run_state = replace(
                    run_state,
                    observations=retain_agent_observations(
                        (*run_state.observations, pending_observation),
                        capability_id=capability_id,
                        target_id=target_id,
                        source_id=source_id,
                    ),
                )
                record(
                    state,
                    AgentControllerLoopRecordStatus.SUCCEEDED,
                    pending_observation.status.value,
                )
                pending_observation = None
                pending_identity = (None, None, None)
                state = AgentControllerLoopState.DECIDE
                continue

            if state is AgentControllerLoopState.CHECK_FINAL:
                if decision is None or decision.final_answer is None:
                    return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)
                completion = self._completion_check.check(
                    raw_request=raw_request,
                    hard_constraints=(
                        session_context.completion_constraints(hard_constraints)
                        if session_context is not None
                        else hard_constraints
                    ),
                    run_state=run_state,
                    final_candidate=decision.final_answer,
                )
                if not completion.passed:
                    assert completion.reason is not None
                    record(
                        state,
                        AgentControllerLoopRecordStatus.FAILED,
                        completion.reason.value,
                    )
                    if (
                        completion_feedback_count
                        >= self._config.max_completion_feedback
                    ):
                        return fail(
                            AgentControllerLoopFailure.COMPLETION_FEEDBACK_LIMIT,
                            state,
                        )
                    completion_feedback_count += 1
                    observation_sequence += 1
                    next_observation(
                        serialize_control_feedback(
                            observation_sequence,
                            status=AgentObservationStatus.INVALID_ACTION,
                            capability_id="harness.control",
                            reason_code=completion.reason.value,
                            recoverable=True,
                        )
                    )
                    state = AgentControllerLoopState.OBSERVE
                    continue
                try:
                    response_text = self._final_boundary(decision.final_answer)
                    if not isinstance(response_text, str) or not response_text.strip():
                        raise ValueError("final boundary returned empty text")
                except Exception:
                    return fail(AgentControllerLoopFailure.FINALIZATION_FAILED, state)
                record(state, AgentControllerLoopRecordStatus.SUCCEEDED, "accepted")
                return done(response_text, "final")

            return fail(AgentControllerLoopFailure.CONTRACT_FAILURE, state)


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    return values if value in values else (*values, value)


def _pass_final_answer(answer: str) -> str:
    return answer


def _failure_text(reason: AgentControllerLoopFailure) -> str:
    if reason is AgentControllerLoopFailure.PROVIDER_FAILURE:
        return "Controller unavailable."
    if reason in {
        AgentControllerLoopFailure.CONTROLLER_ROUND_LIMIT,
        AgentControllerLoopFailure.MODEL_CALL_LIMIT,
        AgentControllerLoopFailure.DISCOVERY_LIMIT,
        AgentControllerLoopFailure.ACTION_BUDGET_EXHAUSTED,
        AgentControllerLoopFailure.CONTROLLER_INPUT_BUDGET_EXHAUSTED,
        AgentControllerLoopFailure.STATE_LIMIT,
        AgentControllerLoopFailure.COMPLETION_FEEDBACK_LIMIT,
    }:
        return "Unable to complete within the available budget."
    return "Unable to safely complete the request."


def _bounded_int(name: str, value: object, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")


__all__ = [
    "AgentControllerLoopConfig",
    "AgentControllerLoopCoordinator",
    "AgentControllerLoopFailure",
    "AgentControllerPromptRecord",
    "AgentControllerLoopRecordStatus",
    "AgentControllerLoopResult",
    "AgentControllerLoopState",
    "AgentControllerLoopStateRecord",
]
