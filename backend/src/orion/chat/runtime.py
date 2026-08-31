"""One model-driven Chat runtime and its streaming canonical tool loop."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from orion.access import LocalAccessAdapter
from orion.chat.context_builder import MAX_CONVERSATION_BYTES, ContextBuilder, _messages_bytes
from orion.chat.conversation_state import ConversationStateManager
from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ContextMessage,
    ModelTurn,
    ModelTurnCompleted,
    ModelUsage,
    RuntimeScope,
    SourceRef,
    TimelineItem,
    ToolDefinition,
    ToolResult,
    citations_are_visible,
    strip_source_citation_markers,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings
from orion.observability import ApplicationLog
from orion.persistence.sqlite import SQLiteStore
from orion.security import redact_public
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
    "ordinary tool call has followed. Emit a safe, in-scope ordinary tool call before giving "
    "terminal prose. The model chooses the exact exposed tool and arguments."
)

_CITATION_CORRECTION_INSTRUCTIONS = (
    "The assistant draft immediately above included a citation that was not returned by a "
    "visible ToolResult. Reconsider the request from the available evidence. If sourced evidence "
    "is needed and none is visible, continue with safe model-chosen tool calls, expanding exact "
    "catalog names when needed. Otherwise regenerate without the invalid citation. Use only exact "
    "visible source_ref_id values and do not repeat, transform, or invent unavailable sources."
)

# A recovery decision is only forced after terminal prose abandons an unresolved
# recovery or capability-action obligation. Two decisions cover a semantic
# recovery followed by one independently recoverable control-plane barrier,
# while keeping the model loop strictly bounded.
_MAX_FORCED_RECOVERY_DECISIONS = 2

MAX_MODEL_REQUEST_PROXY_BYTES = 12_000
_MODEL_REQUEST_ENVELOPE_RESERVE_BYTES = 256


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
    tools: tuple[ToolDefinition, ...], extra_messages: tuple[ContextMessage, ...]
) -> int:
    remaining = (
        MAX_MODEL_REQUEST_PROXY_BYTES
        - _tool_definitions_bytes(tools)
        - _messages_bytes(extra_messages)
        - _MODEL_REQUEST_ENVELOPE_RESERVE_BYTES
    )
    if remaining <= 0:
        raise RequestFailed("Model context exceeds the local safety budget.")
    return min(MAX_CONVERSATION_BYTES, remaining)


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
        # An ordinary tool result resolves a prior recovery obligation unless that
        # result explicitly asks the model to recover again. In particular, a
        # terminal, non-recoverable rejection (for example an unsafe URL) is a
        # complete safe outcome, not a reason to force more model decisions.
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
    ) -> None:
        self._store = store
        self._backend = backend
        self._registry = registry
        self._access = access
        self._runner = ToolRunner(registry)
        self._context_builder = ContextBuilder(store, infrastructure_targets)
        self._conversation_state = ConversationStateManager(store, backend)
        self._application_log = application_log
        self._cancellations: dict[str, asyncio.Event] = {}
        self._pending_content: dict[str, str] = {}
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
        started_at = time.monotonic()
        input_tokens = 0
        output_tokens = 0
        has_complete_usage = True
        citation_correction_attempted = False
        try:
            async with self._session_locks.setdefault(session_id, asyncio.Lock()):
                self._store.start_request(request_id)
                self._store.append_timeline(
                    session_id, request_id, "user_message", {"content": content}
                )
                self._emit(
                    request_id,
                    "request.accepted",
                    {"request_id": request_id, "session_id": session_id},
                )
                settings = self._settings()
                scope = self._runtime_scope(session_id)
                state_preparation = await self._conversation_state.prepare(
                    session_id, settings, cancellation
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
                recovery_decision_next = False
                recovery_guidance_next = False
                citation_correction_next: AssistantMessage | None = None
                while True:
                    self._ensure_not_cancelled(cancellation)
                    self._emit(request_id, "model.started", {})
                    recovery_decision = recovery_decision_next
                    recovery_decision_next = False
                    recovery_guidance = recovery_guidance_next
                    recovery_guidance_next = False
                    citation_correction = citation_correction_next
                    citation_correction_next = None
                    turn, usage, visible_sources = await self._stream_turn(
                        session_id,
                        request_id,
                        settings,
                        scope,
                        cancellation,
                        tool_exposure,
                        recovery_decision=recovery_decision,
                        recovery_guidance=recovery_guidance,
                        capability_action_pending=capability_action_pending,
                        citation_correction=citation_correction,
                    )
                    if usage is None:
                        has_complete_usage = False
                    else:
                        input_tokens += usage.input_tokens
                        output_tokens += usage.output_tokens
                    self._ensure_not_cancelled(cancellation)
                    self._emit(
                        request_id, "model.completed", {"tool_call_count": len(turn.tool_calls)}
                    )
                    recovery_abandoned = (
                        not turn.tool_calls
                        and (recovery_pending or capability_action_pending)
                        and forced_recovery_decisions_used < _MAX_FORCED_RECOVERY_DECISIONS
                        and (not recovery_decision or capability_action_pending)
                    )
                    citation_correction_required = False
                    # A terminal draft that will be replaced by the bounded recovery
                    # decision is not final. Validate only the answer that could be
                    # returned to the caller.
                    if not turn.tool_calls and not recovery_abandoned:
                        try:
                            self._validate_citations(turn, scope, visible_sources)
                        except CitationValidationFailed:
                            assert turn.assistant is not None
                            # A terminal draft with no visible sources can carry stale
                            # provider citation metadata. Give unknown metadata one generic
                            # chance to regenerate while no ToolResult has supplied citation
                            # evidence. Source-free successes and errors do not make an arbitrary
                            # provider identifier a real source. A reference previously returned
                            # in the session, or any currently visible source, remains a strict
                            # integrity failure if it is no longer visible or accessible.
                            if (
                                citation_correction_attempted
                                or visible_sources
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
                                0, round((time.monotonic() - started_at) * 1000)
                            )
                        }
                        if has_complete_usage:
                            metrics["input_tokens"] = input_tokens
                            metrics["output_tokens"] = output_tokens
                    if citation_correction_required:
                        # Do not persist or return a terminal answer until its
                        # citation metadata validates against visible sources.
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
                    if recovery_decision:
                        # A forced decision that emits tools continues the unresolved
                        # obligation into result accounting. A terminal forced decision is
                        # itself the model's permitted final clarification/refusal.
                        recovery_pending = True
                    exposed_before_turn = tool_exposure.exposed_names
                    results: list[tuple[str, ToolResult]] = []
                    for model_call in turn.tool_calls:
                        self._ensure_not_cancelled(cancellation)
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
                        self._emit(
                            request_id,
                            "tool.started",
                            self._tool_activity(
                                model_call.tool_name, model_call.call_id, model_call.arguments
                            ),
                        )
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
                            result = await self._runner.run_async(
                                model_call, scope, cancellation.is_set
                            )
                        self._persist_tool_result(session_id, request_id, result)
                        results.append((model_call.tool_name, result))
                    recovery_pending, capability_action_pending = _next_recovery_state(
                        recovery_pending, capability_action_pending, results
                    )
                    if recovery_pending or capability_action_pending:
                        recovery_guidance_next = True
                    self._emit(request_id, "model.resumed", {})
        except asyncio.CancelledError as error:
            self._store.complete_request(request_id, "cancelled")
            self._emit(request_id, "request.cancelled", {})
            raise RequestCancelled("Request cancelled.") from error
        except ModelBackendError as error:
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
            self._store.complete_request(request_id, "failed", str(error))
            self._emit(request_id, "request.failed", {"message": str(error)})
            raise
        except Exception as error:
            self._fail_unexpected(request_id)
            raise RequestFailed("Request failed unexpectedly.") from error
        finally:
            request = self._store.request(request_id)
            if request is not None and request["status"] in {"queued", "running"}:
                self._fail_unexpected(request_id)
            self._cancellations.pop(request_id, None)
            self._pending_content.pop(request_id, None)

    async def _stream_turn(
        self,
        session_id: str,
        request_id: str,
        settings: ModelSettings,
        scope: RuntimeScope,
        cancellation: asyncio.Event,
        tool_exposure: ToolExposureRequest,
        *,
        recovery_decision: bool = False,
        recovery_guidance: bool = False,
        capability_action_pending: bool = False,
        citation_correction: AssistantMessage | None = None,
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
                    # The provider derives citation metadata from literal markers in text.
                    # Keep the rejected draft's prose for correction, but do not prime the
                    # next turn by echoing evidence markers that validation already rejected.
                    content=strip_source_citation_markers(citation_correction.content),
                    citation_source_ref_ids=(),
                ),
                ContextMessage(role="system", content=_CITATION_CORRECTION_INSTRUCTIONS),
            )
            if citation_correction is not None
            else ()
        )

        model_tools = tool_exposure.model_tools
        extra_messages = (
            *recovery_message,
            *capability_action_message,
            *citation_correction_messages,
        )
        context = self._context_builder.build_with_metadata(
            session_id,
            scope.project_id,
            project_id_is_resolved=True,
            attachment_ids=scope.attachment_ids,
            maximum_bytes=_context_budget_for_turn(model_tools, extra_messages),
        )
        model_messages = (*context.messages, *extra_messages)
        if _model_request_proxy_bytes(model_messages, model_tools) > MAX_MODEL_REQUEST_PROXY_BYTES:
            raise RequestFailed("Model context exceeds the local safety budget.")

        async for event in self._backend.stream(
            model_messages,
            model_tools,
            settings,
            cancellation,
        ):
            self._ensure_not_cancelled(cancellation)
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

    def _persist_tool_result(self, session_id: str, request_id: str, result: ToolResult) -> None:
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

    def _emit(self, request_id: str, event_type: str, payload: dict[str, object]) -> None:
        public_payload = redact_public(payload)
        self._store.emit_event(request_id, event_type, public_payload)
        if self._application_log is not None:
            self._application_log.write(event_type, {"request_id": request_id, **public_payload})

    def _fail_unexpected(self, request_id: str) -> None:
        self._store.complete_request(request_id, "failed", "Request failed unexpectedly.")
        self._emit(request_id, "request.failed", {"message": "Request failed unexpectedly."})

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
