"""One model-driven Chat runtime and its streaming canonical tool loop."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

from orion.access import LocalAccessAdapter
from orion.chat.context_builder import MAX_CONVERSATION_BYTES, ContextBuilder, _messages_bytes
from orion.chat.conversation_state import ConversationStateManager
from orion.chat.deadline import (
    MutationOutcomeUnknown,
    RequestBudget,
    RequestBudgetSettings,
    RequestDeadlineExceeded,
)
from orion.chat.diagnostics import RuntimeDiagnosticSink, model_input_snapshot
from orion.chat.recovery import (
    ReadProgressEvidence,
    RecoverableFailureTracker,
    RecoveryFailureState,
    RecoveryFingerprint,
)
from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ContextMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ModelUsage,
    ReasoningDelta,
    RuntimeScope,
    SourceRef,
    TimelineItem,
    ToolCallDelta,
    ToolDefinition,
    ToolResult,
    citations_are_visible,
    strip_source_citation_markers,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings
from orion.observability import ApplicationLog
from orion.persistence.sqlite import SQLiteStore
from orion.security import redact_public
from orion.tool_runtime.mutation_authorization import MutationAuthorizationPolicy
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolExposureRequest, ToolRegistry
from orion.tool_runtime.runner import ToolRunner


class RequestCancelled(RuntimeError):
    """The user cancelled an in-flight model/tool request."""


class RequestFailed(RuntimeError):
    """A model failure exposed at the request boundary."""


class CitationValidationFailed(RequestFailed):
    """A terminal response cited a source that is not available to the session."""

    public_message = "Orion could not verify the response against available sources."


@dataclass(frozen=True)
class RequestOutcome:
    request_id: str
    assistant_content: str
    status: str = "completed"


@dataclass
class _ModelStreamProgress:
    """Aggregate safe stream-shape facts for one normalized model turn.

    This deliberately receives only canonical ``ModelStreamEvent`` instances.
    It never retains the content or arguments carried by delta events.
    """

    # Every accepted ModelBackend event, including ReasoningDelta and completion.
    first_normalized_event_elapsed_ms: int | None = None
    # Stream deltas only; ModelTurnCompleted alone does not constitute activity.
    first_stream_activity_elapsed_ms: int | None = None
    first_reasoning_delta_elapsed_ms: int | None = None
    first_assistant_delta_elapsed_ms: int | None = None
    first_tool_call_delta_elapsed_ms: int | None = None
    first_stream_activity_kind: str | None = None
    first_actionable_delta_kind: str | None = None
    reasoning_observed_before_first_actionable_delta: bool | None = None
    reasoning_delta_count: int = 0
    reasoning_delta_characters: int = 0
    assistant_delta_count: int = 0
    assistant_delta_characters: int = 0
    tool_call_delta_count: int = 0
    reasoning_milestone_recorded: bool = False

    def observe(self, event: object, elapsed_ms: int) -> str | None:
        if self.first_normalized_event_elapsed_ms is None:
            self.first_normalized_event_elapsed_ms = elapsed_ms
        if isinstance(event, ReasoningDelta):
            self._first_stream_activity("reasoning", elapsed_ms)
            if self.first_reasoning_delta_elapsed_ms is None:
                self.first_reasoning_delta_elapsed_ms = elapsed_ms
            self.reasoning_delta_count += 1
            self.reasoning_delta_characters += len(event.content)
            if self.first_actionable_delta_kind is None and not self.reasoning_milestone_recorded:
                self.reasoning_milestone_recorded = True
                return "reasoning"
            return None
        if isinstance(event, AssistantDelta):
            self._first_stream_activity("assistant", elapsed_ms)
            if self.first_assistant_delta_elapsed_ms is None:
                self.first_assistant_delta_elapsed_ms = elapsed_ms
            self.assistant_delta_count += 1
            self.assistant_delta_characters += len(event.content)
            return "actionable" if self._first_actionable_delta("assistant") else None
        elif isinstance(event, ToolCallDelta):
            self._first_stream_activity("tool_call", elapsed_ms)
            if self.first_tool_call_delta_elapsed_ms is None:
                self.first_tool_call_delta_elapsed_ms = elapsed_ms
            self.tool_call_delta_count += 1
            return "actionable" if self._first_actionable_delta("tool_call") else None
        return None

    def _first_stream_activity(self, kind: str, elapsed_ms: int) -> None:
        if self.first_stream_activity_kind is not None:
            return
        self.first_stream_activity_kind = kind
        self.first_stream_activity_elapsed_ms = elapsed_ms

    def _first_actionable_delta(self, kind: str) -> bool:
        if self.first_actionable_delta_kind is not None:
            return False
        self.first_actionable_delta_kind = kind
        self.reasoning_observed_before_first_actionable_delta = self.reasoning_delta_count > 0
        return True

    def diagnostic_fields(self) -> dict[str, object]:
        """Return the fixed, content-free fields safe to add to a terminal record."""
        return {
            "first_normalized_event_elapsed_ms": self.first_normalized_event_elapsed_ms,
            "first_stream_activity_elapsed_ms": self.first_stream_activity_elapsed_ms,
            "first_stream_activity_kind": self.first_stream_activity_kind,
            "first_reasoning_delta_elapsed_ms": self.first_reasoning_delta_elapsed_ms,
            "first_assistant_delta_elapsed_ms": self.first_assistant_delta_elapsed_ms,
            "first_tool_call_delta_elapsed_ms": self.first_tool_call_delta_elapsed_ms,
            "first_actionable_delta_kind": self.first_actionable_delta_kind,
            "reasoning_observed_before_first_actionable_delta": (
                self.reasoning_observed_before_first_actionable_delta
            ),
            "reasoning_delta_count": self.reasoning_delta_count,
            "reasoning_delta_characters": self.reasoning_delta_characters,
            "assistant_delta_count": self.assistant_delta_count,
            "assistant_delta_characters": self.assistant_delta_characters,
            "tool_call_delta_count": self.tool_call_delta_count,
        }


@dataclass(frozen=True)
class _ActiveModelPhase:
    model_turn_id: str
    started_at: float
    progress: _ModelStreamProgress


_SESSION_CONTINUITY_INSTRUCTIONS = (
    "Visible earlier user messages in this same session are conversation context. "
    "Answer from them directly when relevant. If asked to repeat exact text from a visible "
    "earlier user message, reproduce it verbatim. Do not claim that visible session context "
    "is unavailable merely because no memory or knowledge tool was used."
)

_RECOVERY_DECISION_INSTRUCTIONS = (
    "The preceding ToolResult marked model recovery as required or expanded capability without "
    "an ordinary follow-up, and the request is unresolved. If exposed_for_retry, call that "
    "now-visible tool directly; do not expand it. If not_exposed, expand the same exact failed "
    "tool name and retry the intended operation rather than substituting a different discovery or "
    "metadata tool. For other recoverable outcomes, "
    "either emit the next safe, in-scope tool calls, expanding an unexposed exact catalog name "
    "when needed, or give a final clarification/refusal if recovery is not appropriate. Do not "
    "merely repeat a tool procedure in prose."
)

_CAPABILITY_ACTION_INSTRUCTIONS = (
    "An ordinary capability was successfully expanded for this unresolved request, but no "
    "ordinary tool call has followed. Emit safe, in-scope ordinary tool calls before giving "
    "terminal prose. When multiple relevant exposed read-only tools have all required inputs "
    "already known and none depends on another ToolResult, emit those calls together in this "
    "model turn; do not serialize independent reads merely to inspect each result first. For "
    "dependent calls, obtain prerequisite evidence first. The model chooses the exact exposed "
    "tools and arguments."
)

_RECOVERY_EXHAUSTED_INSTRUCTIONS = (
    "The same recoverable tool failure state has repeated without argument or error progress, "
    "so its bounded recovery budget is exhausted. Do not call tools again for that state. Give "
    "a concise terminal answer stating what could not be verified and what input or evidence is "
    "missing. Do not invent readings, identifiers, targets, or credentials."
)

_POST_OBSERVATION_INSTRUCTIONS = (
    "Review the ordinary ToolResults already returned before selecting further tools. This does "
    "not make other already-independent reads sequential: when relevant exposed read-only tools "
    "have known inputs and do not depend on another result, emit them together in one model "
    "turn rather than waiting to inspect each result first. If the returned results are enough "
    "for a bounded answer, answer now; do not broaden a general assessment merely to make it "
    "exhaustive. Continue only for a specific missing fact that the user requested and an "
    "in-scope tool can obtain. Treat point-in-time resource snapshots only as "
    "readings at their retrieval time: without history, baselines, workload requirements, "
    "thresholds/SLOs, or activity counters, do not infer health, sustained utilization, spare "
    "capacity, workload sufficiency, absence of risk, or absence of swap-in/swap-out activity. "
    "For dated records, "
    "state the explicit query window and returned earliest/latest timestamps. Do not call events "
    "current, recent, or part of a requested reporting period unless their occurred_at values "
    "fall inside that period. Describe failed, empty, or unqueried evidence as a gap instead of "
    "inferring absence. Separate measured facts from unknowns. A low load average is not CPU "
    "utilization or proof of no contention. Free memory is not proof of sufficient capacity. "
    "Do not label readings normal/healthy or invent readiness scores or thresholds. Do not "
    "turn an assumption into a finding, even if labeled as an assumption. If evidence is "
    "omitted from context, report it as unavailable; do not reconstruct values or states."
)

_CITATION_CORRECTION_INSTRUCTIONS = (
    "The assistant draft immediately above included a citation that was not returned by a "
    "visible ToolResult. Reconsider the request from the available evidence. If sourced evidence "
    "is needed and none is visible, continue with safe model-chosen tool calls, expanding exact "
    "catalog names when needed. Otherwise regenerate without the invalid citation. Use only exact "
    "visible source_ref_id values and do not repeat, transform, or invent unavailable sources."
)

# A recovery decision is only forced after terminal prose abandons an unresolved
# recovery or capability-action obligation. This bound is not a tool-call quota;
# successful tool chains remain unrestricted by a fixed call count.
_MAX_FORCED_RECOVERY_DECISIONS = 2
_MODEL_REQUEST_ENVELOPE_RESERVE_BYTES = 256
_INCOMPLETE_FALLBACK = "Orion could not complete a verified response before the request ended."
_RecoveryFingerprint = RecoveryFingerprint


def _tool_definitions_bytes(tools: tuple[ToolDefinition, ...]) -> int:
    return len(
        json.dumps(
            [definition.provider_schema() for definition in tools],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _model_request_proxy_bytes(
    messages: tuple[ContextMessage, ...], tools: tuple[ToolDefinition, ...]
) -> int:
    return (
        _messages_bytes(messages)
        + _tool_definitions_bytes(tools)
        + _MODEL_REQUEST_ENVELOPE_RESERVE_BYTES
    )


def _context_budget_for_turn(
    extra_messages: tuple[ContextMessage, ...],
) -> int:
    remaining = MAX_CONVERSATION_BYTES - _messages_bytes(extra_messages)
    if remaining <= 0:
        raise RequestFailed(
            "Model context exceeds Orion's local safety bound; the current user message was not "
            "silently truncated."
        )
    return remaining


def _recoverable_failure_fingerprint(
    model_call: ModelToolCall, result: ToolResult
) -> _RecoveryFingerprint | None:
    error = result.error
    if error is None or not error.model_recovery_required or error.code == "exposed_for_retry":
        return None
    normalized_arguments = json.dumps(
        model_call.arguments,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    # Retain only a stable digest in request-local recovery history. Call IDs,
    # argument key ordering, and raw argument content must not influence or leak
    # through recurrence evidence.
    arguments_digest = hashlib.sha256(normalized_arguments.encode("utf-8")).hexdigest()
    return model_call.tool_name, arguments_digest, error.code


def _read_progress_evidence(
    model_call: ModelToolCall,
    result: ToolResult,
    definition: ToolDefinition | None,
    observations: dict[tuple[str, str], str],
) -> ReadProgressEvidence | None:
    """Compare a read before model projection; success alone is never progress."""
    if definition is None or definition.operation_kind != "read":
        return None
    progress = result.read_progress
    if result.status != "success" or progress is None or progress.certainty != "confirmed":
        return ReadProgressEvidence(model_call.tool_name, "unknown_progress")
    sources = [
        source.model_dump(mode="json", exclude={"retrieved_at"}) for source in result.sources
    ]
    payload: dict[str, object] = {
        "observation_id": progress.observation_id,
        "version": progress.version,
        "cursor": progress.cursor,
        "coverage": progress.coverage,
        "event_time": progress.event_time.isoformat() if progress.event_time else None,
        "data": result.data,
        "sources": sources,
    }
    # Arguments are evidence only for a handler-declared query coverage; an
    # arbitrary changed argument must not manufacture a recovery barrier.
    if progress.coverage is not None:
        payload["query_semantics"] = model_call.arguments
    snapshot = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    )
    key = (model_call.tool_name, progress.observation_id)
    previous = observations.get(key)
    observations[key] = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    return ReadProgressEvidence(
        model_call.tool_name,
        "confirmed_progress"
        if previous is None or previous != observations[key]
        else "confirmed_no_progress",
    )


def _next_recovery_state(
    recovery_pending: bool,
    capability_action_pending: bool,
    results: list[tuple[str, ToolResult]],
) -> tuple[bool, bool]:
    """Apply one order-independent recovery transition for a model tool-call turn."""
    ordinary_called = any(tool_name != EXPAND_TOOL_NAME for tool_name, _ in results)
    recoverable_error = any(
        result.error is not None and result.error.model_recovery_required for _, result in results
    )
    expansion_succeeded = any(
        tool_name == EXPAND_TOOL_NAME and result.status == "success"
        for tool_name, result in results
    )
    return (
        recoverable_error or (recovery_pending and not ordinary_called),
        (capability_action_pending or expansion_succeeded) and not ordinary_called,
    )


class ChatRuntime:
    def __init__(
        self,
        store: SQLiteStore,
        backend: ModelBackend,
        registry: ToolRegistry,
        access: LocalAccessAdapter,
        infrastructure_targets: tuple[tuple[str, str, str], ...] = (),
        application_log: ApplicationLog | None = None,
        blocked_tool_operation_kinds: frozenset[str] = frozenset(),
        diagnostic_sink: RuntimeDiagnosticSink | None = None,
        request_budget_settings: RequestBudgetSettings | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        deadline_sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        mutation_authorization: MutationAuthorizationPolicy | None = None,
    ) -> None:
        self._store = store
        self._backend = backend
        self._registry = registry
        self._access = access
        self._runner = ToolRunner(registry, blocked_tool_operation_kinds, mutation_authorization)
        self._infrastructure_targets = infrastructure_targets
        self._context_builder = ContextBuilder(store, infrastructure_targets)
        self._conversation_state = ConversationStateManager(store, backend)
        self._application_log = application_log
        self._diagnostic_sink = diagnostic_sink
        self._request_budget_settings = (
            request_budget_settings or RequestBudgetSettings.from_environment()
        )
        self._monotonic_clock = monotonic_clock
        self._deadline_sleeper = deadline_sleeper
        initial_model_tools = registry.new_tool_exposure().model_tools
        self._maximum_model_tool_bytes = _tool_definitions_bytes(
            (*initial_model_tools, *registry.model_definitions())
        )
        self._maximum_model_request_proxy_bytes = (
            MAX_CONVERSATION_BYTES
            + self._maximum_model_tool_bytes
            + _MODEL_REQUEST_ENVELOPE_RESERVE_BYTES
        )
        self._cancellations: dict[str, asyncio.Event] = {}
        self._pending_content: dict[str, str] = {}
        self._queued_at: dict[str, float] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

    async def submit(
        self, session_id: str, content: str, cancellation: asyncio.Event | None = None
    ) -> RequestOutcome:
        request_id = self.begin(session_id, content, cancellation)
        return await self.run(session_id, request_id)

    def begin(
        self, session_id: str, content: str, cancellation: asyncio.Event | None = None
    ) -> str:
        if not self._store.session_exists(session_id):
            raise KeyError(session_id)
        request_id = self._store.create_request(session_id)
        self._cancellations[request_id] = cancellation or asyncio.Event()
        self._pending_content[request_id] = content
        self._queued_at[request_id] = self._monotonic_clock()
        return request_id

    def cancel(self, request_id: str) -> bool:
        cancellation = self._cancellations.get(request_id)
        if cancellation is None:
            return False
        cancellation.set()
        return True

    async def run(self, session_id: str, request_id: str) -> RequestOutcome:
        cancellation = self._cancellations.get(request_id)
        content = self._pending_content.get(request_id)
        if cancellation is None or content is None:
            request = self._store.request(request_id)
            if request is not None and request["status"] in {"queued", "running"}:
                self._fail_unexpected(request_id)
            raise RequestFailed("Request is unavailable.")
        started_at = 0.0
        budget: RequestBudget | None = None
        input_tokens = 0
        output_tokens = 0
        has_complete_usage = True
        citation_correction_attempted = False
        active_model_phase: _ActiveModelPhase | None = None
        terminal_final_started = False
        observed_source_ref_ids: set[str] = set()
        try:
            async with self._session_locks.setdefault(session_id, asyncio.Lock()):
                self._store.start_request(request_id)
                budget = RequestBudget.start(
                    self._request_budget_settings,
                    clock=self._monotonic_clock,
                    sleeper=self._deadline_sleeper,
                )
                started_at = budget.started_monotonic
                self._store.append_timeline(
                    session_id, request_id, "user_message", {"content": content}
                )
                self._emit(
                    request_id,
                    "request.accepted",
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "queue_wait_ms": max(
                            0,
                            round(
                                (started_at - self._queued_at.get(request_id, started_at)) * 1000
                            ),
                        ),
                    },
                )
                settings = self._settings()
                scope = self._runtime_scope(session_id)
                state_preparation = await budget.await_work(
                    self._conversation_state.prepare(session_id, settings, cancellation),
                    cancellation,
                    phase="conversation_state_preparation",
                )
                if state_preparation.attempted:
                    if state_preparation.usage is None:
                        has_complete_usage = False
                    else:
                        input_tokens += state_preparation.usage.input_tokens
                        output_tokens += state_preparation.usage.output_tokens
                tool_exposure = self._registry.new_tool_exposure()
                recovery_pending = False
                capability_action_pending = False
                forced_recovery_decisions_used = 0
                recovery_tracker = RecoverableFailureTracker(
                    repeat_limit=self._request_budget_settings.recovery_repeat_limit,
                    cycle_repeat_limit=self._request_budget_settings.recovery_cycle_repeat_limit,
                )
                recovery_decision_next = False
                read_observations: dict[tuple[str, str], str] = {}
                recovery_guidance_next = False
                recovery_exhausted_next = False
                terminal_final_pending = False
                observation_review_next = False
                citation_correction_next: AssistantMessage | None = None
                model_turn_number = 0
                while True:
                    self._ensure_not_cancelled(cancellation)
                    budget.ensure_work_available("model")
                    terminal_final = terminal_final_pending
                    terminal_final_pending = False
                    terminal_final_started = terminal_final_started or terminal_final
                    model_turn_number += 1
                    model_turn_id = f"{request_id}:{model_turn_number}:{uuid.uuid4().hex[:8]}"
                    model_started_at = self._monotonic_clock()
                    model_stream_progress = _ModelStreamProgress()
                    self._emit(request_id, "model.started", {"model_turn_id": model_turn_id})
                    active_model_phase = _ActiveModelPhase(
                        model_turn_id, model_started_at, model_stream_progress
                    )
                    recovery_decision = recovery_decision_next
                    recovery_decision_next = False
                    recovery_guidance = recovery_guidance_next
                    recovery_guidance_next = False
                    citation_correction = citation_correction_next
                    citation_correction_next = None
                    recovery_exhausted = recovery_exhausted_next
                    recovery_exhausted_next = False
                    observation_review = observation_review_next
                    observation_review_next = False
                    turn, usage, visible_sources = await budget.await_work(
                        self._stream_turn(
                            session_id,
                            request_id,
                            settings,
                            scope,
                            cancellation,
                            tool_exposure,
                            model_turn_id=model_turn_id,
                            model_started_at=model_started_at,
                            model_stream_progress=model_stream_progress,
                            recovery_decision=recovery_decision,
                            recovery_guidance=recovery_guidance,
                            capability_action_pending=capability_action_pending,
                            citation_correction=citation_correction,
                            recovery_exhausted=recovery_exhausted or terminal_final,
                            terminal_final=terminal_final,
                            observation_review=observation_review,
                        ),
                        cancellation,
                        phase="model",
                    )
                    if usage is None:
                        has_complete_usage = False
                    else:
                        input_tokens += usage.input_tokens
                        output_tokens += usage.output_tokens
                    self._ensure_not_cancelled(cancellation)
                    completed_elapsed_ms = self._elapsed_ms(model_started_at)
                    self._emit(
                        request_id,
                        "model.completed",
                        {
                            "model_turn_id": model_turn_id,
                            "tool_call_count": len(turn.tool_calls),
                            "elapsed_ms": completed_elapsed_ms,
                        },
                    )
                    completed_diagnostic: dict[str, object] = {
                        "request_id": request_id,
                        "model_turn_id": model_turn_id,
                        "phase": "model",
                        "status": "completed",
                        "elapsed_ms": completed_elapsed_ms,
                        "completed_elapsed_ms": completed_elapsed_ms,
                        "tool_call_count": len(turn.tool_calls),
                        **model_stream_progress.diagnostic_fields(),
                    }
                    first_event_elapsed_ms = model_stream_progress.first_normalized_event_elapsed_ms
                    completed_diagnostic["first_normalized_event_to_completed_elapsed_ms"] = (
                        max(0, completed_elapsed_ms - first_event_elapsed_ms)
                        if first_event_elapsed_ms is not None
                        else None
                    )
                    if usage is not None:
                        completed_diagnostic["input_tokens"] = usage.input_tokens
                        completed_diagnostic["output_tokens"] = usage.output_tokens
                    self._record_diagnostic(completed_diagnostic)
                    active_model_phase = None
                    if terminal_final:
                        if turn.tool_calls or turn.assistant is None:
                            return self._complete_incomplete(
                                session_id,
                                request_id,
                                "terminal_turn_did_not_return_an_answer",
                                observed_source_ref_ids,
                            )
                        try:
                            self._validate_citations(turn, scope, visible_sources)
                        except CitationValidationFailed:
                            return self._complete_incomplete(
                                session_id,
                                request_id,
                                "terminal_turn_has_unavailable_citation",
                                observed_source_ref_ids,
                            )
                        terminal_metrics: dict[str, int] = {
                            "response_time_ms": max(
                                0, round((self._monotonic_clock() - started_at) * 1000)
                            )
                        }
                        if has_complete_usage:
                            terminal_metrics["input_tokens"] = input_tokens
                            terminal_metrics["output_tokens"] = output_tokens
                        assistant_item = self._persist_assistant_turn(
                            session_id, request_id, turn, terminal_metrics
                        )
                        self._emit(
                            request_id,
                            "assistant.message",
                            {
                                "item": assistant_item.model_dump(mode="json"),
                                "content": redact_public(turn.assistant.content),
                            },
                        )
                        self._store.complete_request(request_id, "completed")
                        self._emit(request_id, "request.completed", {})
                        return RequestOutcome(
                            request_id=request_id, assistant_content=turn.assistant.content
                        )
                    recovery_abandoned = (
                        not turn.tool_calls
                        and (recovery_pending or capability_action_pending)
                        and forced_recovery_decisions_used < _MAX_FORCED_RECOVERY_DECISIONS
                        and not recovery_decision
                    )
                    citation_correction_required = False
                    if not turn.tool_calls and not recovery_abandoned:
                        try:
                            self._validate_citations(turn, scope, visible_sources)
                        except CitationValidationFailed:
                            assert turn.assistant is not None
                            if (
                                citation_correction_attempted
                                or self._citation_references_were_observed(
                                    session_id, turn.assistant.citation_source_ref_ids
                                )
                            ):
                                raise
                            citation_correction_attempted = True
                            citation_correction_required = True
                    metrics: dict[str, int] | None = None
                    if not turn.tool_calls and not recovery_abandoned:
                        metrics = {
                            "response_time_ms": max(
                                0, round((self._monotonic_clock() - started_at) * 1000)
                            )
                        }
                        if has_complete_usage:
                            metrics["input_tokens"] = input_tokens
                            metrics["output_tokens"] = output_tokens
                    if citation_correction_required:
                        assert turn.assistant is not None
                        citation_correction_next = turn.assistant
                        self._emit(request_id, "model.resumed", {})
                        continue
                    if (
                        not turn.tool_calls
                        and capability_action_pending
                        and forced_recovery_decisions_used >= _MAX_FORCED_RECOVERY_DECISIONS
                    ):
                        raise RequestFailed(
                            "Model did not make an ordinary tool decision after successful "
                            "capability expansion."
                        )
                    assistant_item = self._persist_assistant_turn(
                        session_id, request_id, turn, metrics
                    )
                    if turn.assistant is not None:
                        self._emit(
                            request_id,
                            "assistant.message",
                            {
                                "item": assistant_item.model_dump(mode="json"),
                                "content": redact_public(turn.assistant.content),
                            },
                        )
                    if not turn.tool_calls:
                        if turn.assistant is None:
                            raise RuntimeError("Model returned an invalid terminal turn.")
                        if recovery_abandoned:
                            recovery_pending = False
                            forced_recovery_decisions_used += 1
                            recovery_decision_next = True
                            self._emit(request_id, "model.resumed", {})
                            continue
                        self._store.complete_request(request_id, "completed")
                        self._emit(request_id, "request.completed", {})
                        return RequestOutcome(
                            request_id=request_id, assistant_content=turn.assistant.content
                        )
                    read_progress: list[ReadProgressEvidence] = []
                    if recovery_decision:
                        recovery_pending = True
                    exposed_before_turn = tool_exposure.exposed_names
                    results: list[tuple[str, ToolResult]] = []
                    recoverable_fingerprints: list[_RecoveryFingerprint] = []
                    for model_call in turn.tool_calls:
                        self._ensure_not_cancelled(cancellation)
                        budget.ensure_work_available("tool")
                        tool_started_at = self._monotonic_clock()
                        definition = self._registry.definition(model_call.tool_name)
                        self._store.append_timeline(
                            session_id,
                            request_id,
                            "tool_call",
                            {
                                "arguments": model_call.arguments,
                                "operation_kind": definition.operation_kind
                                if definition
                                else "read",
                            },
                            call_id=model_call.call_id,
                            tool_name=model_call.tool_name,
                        )
                        tool_activity = self._tool_activity(
                            model_call.tool_name, model_call.call_id, model_call.arguments
                        )
                        tool_activity["elapsed_ms"] = self._elapsed_ms(tool_started_at)
                        self._emit(request_id, "tool.started", tool_activity)
                        self._record_diagnostic(
                            {
                                "request_id": request_id,
                                "model_turn_id": model_turn_id,
                                "tool_call_id": model_call.call_id,
                                "tool_name": model_call.tool_name,
                                "phase": "tool",
                                "status": "started",
                                "elapsed_ms": self._elapsed_ms(tool_started_at),
                            }
                        )
                        mutation_interruption: MutationOutcomeUnknown | None = None
                        if model_call.tool_name == EXPAND_TOOL_NAME:
                            result = tool_exposure.expand(model_call)
                        elif definition is None:
                            result = ToolResult.failure(
                                model_call.call_id,
                                model_call.tool_name,
                                "not_found",
                                "Unknown registered tool.",
                            )
                        elif model_call.tool_name not in exposed_before_turn:
                            result = tool_exposure.expose_for_retry(model_call)
                        else:
                            try:
                                result = await budget.await_work(
                                    self._runner.run_async(
                                        model_call,
                                        scope,
                                        lambda: (
                                            cancellation.is_set()
                                            or budget.remaining_work_seconds() <= 0
                                        ),
                                        partial(self._audit_authorization, request_id, model_call),
                                    ),
                                    cancellation,
                                    phase="tool",
                                    preserve_on_interrupt=definition.operation_kind == "mutation",
                                )
                            except MutationOutcomeUnknown as error:
                                mutation_interruption = error
                                result = ToolResult.failure(
                                    model_call.call_id,
                                    model_call.tool_name,
                                    "outcome_unknown",
                                    "The mutation outcome could not be verified before the "
                                    "request deadline.",
                                )
                        self._persist_tool_result(
                            session_id, request_id, result, self._elapsed_ms(tool_started_at)
                        )
                        self._record_diagnostic(
                            {
                                "request_id": request_id,
                                "model_turn_id": model_turn_id,
                                "tool_call_id": model_call.call_id,
                                "tool_name": model_call.tool_name,
                                "phase": "tool",
                                "status": "completed" if result.status == "success" else "failed",
                                "elapsed_ms": self._elapsed_ms(tool_started_at),
                                "canonical_result": result.model_dump(mode="json"),
                            }
                        )
                        results.append((model_call.tool_name, result))
                        observed_source_ref_ids.update(
                            source.source_ref_id for source in result.sources
                        )
                        evidence = _read_progress_evidence(
                            model_call, result, definition, read_observations
                        )
                        if evidence is not None:
                            read_progress.append(evidence)
                        if mutation_interruption is not None:
                            if mutation_interruption.cancelled:
                                raise asyncio.CancelledError
                            raise RequestDeadlineExceeded("tool")
                        if definition is not None and definition.operation_kind == "mutation":
                            if cancellation.is_set():
                                raise asyncio.CancelledError
                            budget.ensure_work_available("tool")
                        fingerprint = _recoverable_failure_fingerprint(model_call, result)
                        if fingerprint is not None:
                            recoverable_fingerprints.append(fingerprint)
                    ordinary_nonrecoverable_result = any(
                        tool_name != EXPAND_TOOL_NAME
                        and (
                            result.status == "success"
                            or result.error is None
                            or not result.error.model_recovery_required
                        )
                        for tool_name, result in results
                    )
                    recoverable_failure_state: RecoveryFailureState = tuple(
                        sorted(recoverable_fingerprints)
                    )
                    recovery_stall = recovery_tracker.observe(
                        recoverable_failure_state,
                        read_progress=tuple(read_progress),
                    )
                    recovery_pending, capability_action_pending = _next_recovery_state(
                        recovery_pending, capability_action_pending, results
                    )
                    if recovery_stall is not None:
                        recovery_pending = False
                        self._emit(
                            request_id,
                            "recovery.stalled",
                            {
                                "reason": recovery_stall.reason,
                                "occurrences": recovery_stall.occurrences,
                                "cycle_length": recovery_stall.cycle_length,
                            },
                        )
                        capability_action_pending = False
                        recovery_guidance_next = False
                        recovery_exhausted_next = True
                        terminal_final_pending = True
                    elif recovery_pending or capability_action_pending:
                        recovery_guidance_next = True
                    observation_review_next = ordinary_nonrecoverable_result
                    self._emit(request_id, "model.resumed", {})
        except RequestDeadlineExceeded as error:
            if active_model_phase is not None:
                self._record_diagnostic(
                    {
                        "request_id": request_id,
                        "model_turn_id": active_model_phase.model_turn_id,
                        "phase": "model",
                        "status": "timed_out",
                        "elapsed_ms": self._elapsed_ms(active_model_phase.started_at),
                        **active_model_phase.progress.diagnostic_fields(),
                    }
                )
            return self._complete_incomplete(
                session_id,
                request_id,
                "request_deadline_exceeded",
                observed_source_ref_ids,
                phase=error.phase,
                elapsed_ms=budget.elapsed_ms() if budget is not None else 0,
            )
        except asyncio.CancelledError as error:
            if active_model_phase is not None:
                self._record_diagnostic(
                    {
                        "request_id": request_id,
                        "model_turn_id": active_model_phase.model_turn_id,
                        "phase": "model",
                        "status": "cancelled",
                        "elapsed_ms": self._elapsed_ms(active_model_phase.started_at),
                        **active_model_phase.progress.diagnostic_fields(),
                    }
                )
            self._store.complete_request(request_id, "cancelled")
            self._emit(request_id, "request.cancelled", {})
            raise RequestCancelled("Request cancelled.") from error
        except ModelBackendError as error:
            if terminal_final_started:
                return self._complete_incomplete(
                    session_id,
                    request_id,
                    "terminal_model_failure",
                    observed_source_ref_ids,
                    model_error_kind=error.kind.value,
                )
            if active_model_phase is not None:
                self._record_diagnostic(
                    {
                        "request_id": request_id,
                        "model_turn_id": active_model_phase.model_turn_id,
                        "phase": "model",
                        "status": "failed",
                        "elapsed_ms": self._elapsed_ms(active_model_phase.started_at),
                        **active_model_phase.progress.diagnostic_fields(),
                    }
                )
            self._store.append_timeline(
                session_id,
                request_id,
                "runtime_notice",
                {
                    "stage": "model",
                    "status": "failed",
                    "error_kind": error.kind.value,
                },
            )
            self._store.complete_request(request_id, "failed", str(error))
            self._emit(
                request_id,
                "request.failed",
                {"message": str(error), "model_error_kind": error.kind.value},
            )
            raise RequestFailed(str(error)) from error
        except CitationValidationFailed as error:
            self._store.append_timeline(
                session_id,
                request_id,
                "runtime_notice",
                {
                    "stage": "citation_validation",
                    "status": "failed",
                    "error_kind": "unavailable_source",
                    "citation_correction_attempted": citation_correction_attempted,
                },
            )
            self._store.complete_request(request_id, "failed", str(error))
            self._emit(
                request_id,
                "request.failed",
                {"message": CitationValidationFailed.public_message},
            )
            raise
        except RequestFailed as error:
            if terminal_final_started:
                return self._complete_incomplete(
                    session_id,
                    request_id,
                    "terminal_finalization_failed",
                    observed_source_ref_ids,
                )
            if active_model_phase is not None:
                self._record_diagnostic(
                    {
                        "request_id": request_id,
                        "model_turn_id": active_model_phase.model_turn_id,
                        "phase": "model",
                        "status": "failed",
                        "elapsed_ms": self._elapsed_ms(active_model_phase.started_at),
                        **active_model_phase.progress.diagnostic_fields(),
                    }
                )
            self._store.complete_request(request_id, "failed", str(error))
            self._emit(request_id, "request.failed", {"message": str(error)})
            raise
        except Exception as error:
            if terminal_final_started:
                return self._complete_incomplete(
                    session_id,
                    request_id,
                    "terminal_finalization_failed",
                    observed_source_ref_ids,
                )
            self._fail_unexpected(request_id)
            raise RequestFailed("Request failed unexpectedly.") from error
        finally:
            request = self._store.request(request_id)
            if request is not None and request["status"] in {"queued", "running"}:
                self._fail_unexpected(request_id)
            self._cancellations.pop(request_id, None)
            self._pending_content.pop(request_id, None)
            self._queued_at.pop(request_id, None)

    async def _stream_turn(
        self,
        session_id: str,
        request_id: str,
        settings: ModelSettings,
        scope: RuntimeScope,
        cancellation: asyncio.Event,
        tool_exposure: ToolExposureRequest,
        *,
        model_turn_id: str,
        model_started_at: float,
        model_stream_progress: _ModelStreamProgress,
        recovery_decision: bool = False,
        recovery_guidance: bool = False,
        capability_action_pending: bool = False,
        citation_correction: AssistantMessage | None = None,
        recovery_exhausted: bool = False,
        terminal_final: bool = False,
        observation_review: bool = False,
    ) -> tuple[ModelTurn, ModelUsage | None, tuple[SourceRef, ...]]:
        completed_turn: ModelTurn | None = None
        completed_usage: ModelUsage | None = None
        recovery_message = (
            (ContextMessage(role="system", content=_RECOVERY_DECISION_INSTRUCTIONS),)
            if recovery_decision or recovery_guidance
            else ()
        )
        capability_action_message = (
            (ContextMessage(role="system", content=_CAPABILITY_ACTION_INSTRUCTIONS),)
            if (recovery_decision or recovery_guidance) and capability_action_pending
            else ()
        )
        citation_correction_messages = (
            (
                ContextMessage(
                    role="assistant",
                    content=strip_source_citation_markers(citation_correction.content),
                    citation_source_ref_ids=(),
                ),
                ContextMessage(role="system", content=_CITATION_CORRECTION_INSTRUCTIONS),
            )
            if citation_correction is not None
            else ()
        )

        recovery_exhausted_message = (
            (ContextMessage(role="system", content=_RECOVERY_EXHAUSTED_INSTRUCTIONS),)
            if recovery_exhausted
            else ()
        )
        observation_review_message = (
            (ContextMessage(role="system", content=_POST_OBSERVATION_INSTRUCTIONS),)
            if observation_review
            else ()
        )
        prior_user_turn_exists = (
            sum(item.kind == "user_message" for item in self._store.timeline(session_id)) > 1
        )
        session_continuity_message = (
            (
                ContextMessage(
                    role="system",
                    content=_SESSION_CONTINUITY_INSTRUCTIONS,
                ),
            )
            if prior_user_turn_exists
            else ()
        )

        model_tools = () if recovery_exhausted or terminal_final else tool_exposure.model_tools
        extra_messages = (
            *session_continuity_message,
            *recovery_message,
            *capability_action_message,
            *recovery_exhausted_message,
            *observation_review_message,
            *citation_correction_messages,
        )
        context = self._context_builder.build_with_metadata(
            session_id,
            scope.project_id,
            project_id_is_resolved=True,
            attachment_ids=scope.attachment_ids,
            maximum_bytes=_context_budget_for_turn(extra_messages),
            strict_total_budget=True,
        )
        model_messages = (*context.messages, *extra_messages)
        if _messages_bytes(model_messages) > MAX_CONVERSATION_BYTES:
            raise RequestFailed(
                "Model context exceeds Orion's local safety bound; the current user message was "
                "not silently truncated."
            )
        if (
            _model_request_proxy_bytes(model_messages, model_tools)
            > self._maximum_model_request_proxy_bytes
        ):
            raise RequestFailed(
                "Model context exceeds Orion's local safety bound; the current user message was "
                "not silently truncated."
            )

        self._record_diagnostic(
            {
                "request_id": request_id,
                "model_turn_id": model_turn_id,
                "phase": "model",
                "status": "started",
                "elapsed_ms": self._elapsed_ms(model_started_at),
                "model_input": model_input_snapshot(
                    model_messages,
                    tuple(tool.name for tool in model_tools),
                    tuple(source.source_ref_id for source in context.visible_sources),
                    _model_request_proxy_bytes(model_messages, model_tools),
                ),
            }
        )

        async for event in self._backend.stream(
            model_messages,
            model_tools,
            settings,
            cancellation,
        ):
            self._ensure_not_cancelled(cancellation)
            event_elapsed_ms = self._elapsed_ms(model_started_at)
            milestone_kind = model_stream_progress.observe(event, event_elapsed_ms)
            if milestone_kind is not None:
                self._record_diagnostic(
                    {
                        "request_id": request_id,
                        "model_turn_id": model_turn_id,
                        "phase": "model",
                        "status": "stream_progress",
                        "elapsed_ms": event_elapsed_ms,
                        "stream_progress_milestone": milestone_kind,
                        **model_stream_progress.diagnostic_fields(),
                    }
                )
            if isinstance(event, AssistantDelta):
                self._emit(request_id, "assistant.delta", {"content": event.content})
            elif isinstance(event, ModelTurnCompleted):
                completed_turn = event.turn
                completed_usage = event.usage
        if completed_turn is None:
            raise ModelBackendError("Model stream ended without a completed turn.")
        return completed_turn, completed_usage, context.visible_sources

    def _runtime_scope(self, session_id: str) -> RuntimeScope:
        identity = self._store.session_identity(session_id)
        if identity is None:
            raise RequestFailed("Session is unavailable.")
        principal = self._access.principal_for_session(
            str(identity["principal_id"]), str(identity["workspace_id"])
        )
        return RuntimeScope(
            session_id=session_id,
            project_id=identity["project_id"],
            attachment_ids=self._store.session_attachment_ids(session_id),
            principal_id=principal.principal_id,
            workspace_id=principal.workspace_id,
        )

    def _settings(self) -> ModelSettings:
        stored = self._store.active_model_config()
        if stored is None:
            raise RequestFailed("No active OpenAI-compatible model configuration.")
        return ModelSettings.model_validate(
            {
                "provider_type": stored["provider_type"],
                "base_url": stored["base_url"],
                "model_id": stored["model_id"],
                "api_key": stored["api_key"],
                "reasoning_mode": stored["reasoning_mode"],
            }
        )

    def _persist_assistant_turn(
        self,
        session_id: str,
        request_id: str,
        turn: ModelTurn,
        metrics: dict[str, int] | None = None,
    ) -> TimelineItem:
        payload: dict[str, object] = {
            "content": redact_public(turn.assistant.content) if turn.assistant is not None else "",
            "citation_source_ref_ids": (
                list(redact_public(turn.assistant.citation_source_ref_ids))
                if turn.assistant is not None
                else []
            ),
            "tool_calls": [call.model_dump(mode="json") for call in turn.tool_calls],
        }
        if metrics is not None:
            payload["metrics"] = metrics
        return self._store.append_timeline(
            session_id,
            request_id,
            "assistant_message",
            payload,
        )

    def _persist_tool_result(
        self, session_id: str, request_id: str, result: ToolResult, elapsed_ms: int
    ) -> None:
        self._store.append_timeline(
            session_id,
            request_id,
            "tool_result",
            {"result": result.model_dump(mode="json")},
            call_id=result.call_id,
            tool_name=result.tool_name,
        )
        event_type = "tool.completed" if result.status == "success" else "tool.failed"
        payload: dict[str, object] = {
            "call_id": result.call_id,
            "tool_name": result.tool_name,
            "status": result.status,
        }
        if result.error is not None and result.error.code == "operation_blocked":
            payload["error_code"] = result.error.code
        payload["elapsed_ms"] = elapsed_ms
        definition = self._registry.definition(result.tool_name)
        if definition is not None and result.tool_name.split(".", 1)[0] in {
            "linux",
            "grafana",
            "zabbix",
        }:
            payload["operation_kind"] = definition.operation_kind
            if isinstance(result.data, dict):
                target_ref = result.data.get("target_ref")
                if isinstance(target_ref, str):
                    payload["target_ref"] = target_ref
                if "changed" in result.data:
                    payload["changed"] = result.data["changed"]
                verification = result.data.get("verification")
                if isinstance(verification, dict):
                    payload["verification"] = verification.get("status")
            if result.error is not None and result.error.code == "outcome_unknown":
                payload["outcome_unknown"] = True
        self._emit(request_id, event_type, payload)

    def _tool_activity(
        self, tool_name: str, call_id: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        """Emit only deterministic non-secret infrastructure activity metadata."""
        payload: dict[str, object] = {"call_id": call_id, "tool_name": tool_name}
        definition = self._registry.definition(tool_name)
        if definition is not None and tool_name.split(".", 1)[0] in {
            "linux",
            "grafana",
            "zabbix",
        }:
            payload["operation_kind"] = definition.operation_kind
            target_ref = arguments.get("target_ref")
            if isinstance(target_ref, str):
                payload["target_ref"] = target_ref
        return payload

    def _audit_authorization(self, request_id: str, call: ModelToolCall, allowed: bool) -> None:
        payload: dict[str, object] = {
            "call_id": call.call_id,
            "tool_name": call.tool_name,
            "operation_kind": "mutation",
            "decision": "allow" if allowed else "deny",
        }
        # Only a configured identity may appear in authorization audit output.
        family = call.tool_name.partition(".")[0]
        target_ref = call.arguments.get("target_ref")
        if any(
            target_family == family and target == target_ref
            for target_family, target, _ in self._infrastructure_targets
        ):
            payload["target_ref"] = target_ref
        self._emit(request_id, "tool.authorization", payload)

    def diagnostics(self, request_id: str) -> dict[str, object] | None:
        """Return opt-in diagnostic records without making them runtime state."""
        sink = self._diagnostic_sink
        records = getattr(sink, "records", None)
        if not callable(records):
            return None
        try:
            value = records(request_id)
        except Exception:
            return None
        return value if isinstance(value, dict) else None

    def _record_diagnostic(self, record: dict[str, object]) -> None:
        if self._diagnostic_sink is None:
            return
        try:
            self._diagnostic_sink.record(record)
        except Exception:
            # Diagnostics are never allowed to affect dispatch or cancellation.
            return

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, round((self._monotonic_clock() - started_at) * 1000))

    def _emit(self, request_id: str, event_type: str, payload: dict[str, object]) -> None:
        public_payload = redact_public(payload)
        self._store.emit_event(request_id, event_type, public_payload)
        if self._application_log is not None:
            self._application_log.write(event_type, {"request_id": request_id, **public_payload})

    def _fail_unexpected(self, request_id: str) -> None:
        self._store.complete_request(request_id, "failed", "Request failed unexpectedly.")
        self._emit(request_id, "request.failed", {"message": "Request failed unexpectedly."})

    def _complete_incomplete(
        self,
        session_id: str,
        request_id: str,
        stop_reason: str,
        observed_source_ref_ids: set[str],
        **details: object,
    ) -> RequestOutcome:
        """Persist one data-free terminal fallback without starting more work."""
        references = sorted(observed_source_ref_ids)
        notice: dict[str, object] = {
            "stage": "terminal",
            "status": "incomplete",
            "stop_reason": stop_reason,
            "observation_source_ref_ids": references,
            **details,
        }
        self._store.append_timeline(session_id, request_id, "runtime_notice", notice)
        assistant_item = self._store.append_timeline(
            session_id,
            request_id,
            "assistant_message",
            {
                "content": _INCOMPLETE_FALLBACK,
                "citation_source_ref_ids": [],
                "tool_calls": [],
                "incomplete": True,
            },
        )
        self._store.complete_request(request_id, "incomplete", _INCOMPLETE_FALLBACK)
        self._emit(
            request_id,
            "assistant.message",
            {
                "item": assistant_item.model_dump(mode="json"),
                "content": _INCOMPLETE_FALLBACK,
            },
        )
        self._emit(
            request_id,
            "request.incomplete",
            {"stop_reason": stop_reason, "observation_source_ref_ids": references, **details},
        )
        return RequestOutcome(
            request_id=request_id,
            assistant_content=_INCOMPLETE_FALLBACK,
            status="incomplete",
        )

    def _validate_citations(
        self, turn: ModelTurn, scope: RuntimeScope, visible_sources: tuple[SourceRef, ...]
    ) -> None:
        if turn.assistant is None or not turn.assistant.citation_source_ref_ids:
            return
        sources_by_id = {source.source_ref_id: source for source in visible_sources}
        if not citations_are_visible(turn.assistant.citation_source_ref_ids, set(sources_by_id)):
            raise CitationValidationFailed("Assistant cited an unavailable source.")
        attachment_ids = self._store.session_attachment_ids(scope.session_id)
        for source_ref_id in turn.assistant.citation_source_ref_ids:
            source = sources_by_id[source_ref_id]
            if source.source_kind == "internet" and source.document_id is None and source.url:
                continue
            if source.source_kind in {"linux", "grafana", "zabbix"} and source.document_id is None:
                continue
            if source.document_id is None:
                raise CitationValidationFailed("Assistant cited an unavailable source.")
            document = self._store.document(source.document_id)
            accessible = (
                document is not None
                and document["status"] == "ready"
                and (
                    (
                        document["session_id"] == scope.session_id
                        and document["attachment_id"] in attachment_ids
                        and source.source_kind == "session"
                        and source.source_id == scope.session_id
                    )
                    or (
                        document["project_id"] == scope.project_id
                        and scope.project_id is not None
                        and source.source_kind == "project"
                        and source.source_id == scope.project_id
                    )
                )
            )
            if not accessible:
                raise CitationValidationFailed("Assistant cited an unavailable source.")

    def _citation_references_were_observed(
        self, session_id: str, citation_source_ref_ids: tuple[str, ...]
    ) -> bool:
        """Return whether a rejected citation reuses any session-observed source reference."""
        rejected = set(citation_source_ref_ids)
        if not rejected:
            return False
        for item in self._store.timeline(session_id):
            if item.kind != "tool_result":
                continue
            try:
                result = ToolResult.model_validate(item.payload["result"])
            except (KeyError, TypeError, ValueError):
                continue
            if any(source.source_ref_id in rejected for source in result.sources):
                return True
        return False

    @staticmethod
    def _ensure_not_cancelled(cancellation: asyncio.Event) -> None:
        if cancellation.is_set():
            raise asyncio.CancelledError
