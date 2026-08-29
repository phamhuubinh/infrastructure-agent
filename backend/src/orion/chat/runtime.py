"""One model-driven Chat runtime and its streaming canonical tool loop."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from orion.access import LocalAccessAdapter
from orion.chat.context_builder import ContextBuilder
from orion.chat.conversation_state import ConversationStateManager
from orion.contracts import (
    AssistantDelta,
    ContextMessage,
    ModelTurn,
    ModelTurnCompleted,
    ModelUsage,
    RuntimeScope,
    SourceRef,
    TimelineItem,
    ToolResult,
    citations_are_visible,
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


@dataclass(frozen=True)
class RequestOutcome:
    request_id: str
    assistant_content: str


_RECOVERY_DECISION_INSTRUCTIONS = (
    "The preceding ToolResult marked model recovery as required and the request is unresolved. "
    "Either emit the next safe, in-scope tool calls, expanding an unexposed exact catalog name "
    "when needed, or give a final clarification/refusal if recovery is not appropriate. Do not "
    "merely repeat a tool procedure in prose."
)


# A recovery decision is only forced after terminal prose abandons a ToolResult
# that explicitly requested model recovery. Two decisions cover a semantic
# recovery followed by one independently recoverable control-plane barrier
# (for example, progressive tool exposure), while keeping the model loop
# strictly bounded.
_MAX_FORCED_RECOVERY_DECISIONS = 2


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
                forced_recovery_decisions_used = 0
                recovery_decision_next = False
                while True:
                    self._ensure_not_cancelled(cancellation)
                    self._emit(request_id, "model.started", {})
                    recovery_decision = recovery_decision_next
                    recovery_decision_next = False
                    turn, usage, visible_sources = await self._stream_turn(
                        session_id,
                        request_id,
                        settings,
                        scope,
                        cancellation,
                        tool_exposure,
                        recovery_decision=recovery_decision,
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
                    self._validate_citations(turn, scope, visible_sources)
                    recovery_abandoned = (
                        not turn.tool_calls
                        and recovery_pending
                        and not recovery_decision
                        and forced_recovery_decisions_used < _MAX_FORCED_RECOVERY_DECISIONS
                    )
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
                            result = ToolResult.failure(
                                model_call.call_id,
                                model_call.tool_name,
                                "not_exposed",
                                "Tool is not exposed. Call orion.tools.expand with this exact "
                                "catalog name, then retry.",
                                model_recovery_required=True,
                            )
                        else:
                            result = await self._runner.run_async(
                                model_call, scope, cancellation.is_set
                            )
                        self._persist_tool_result(session_id, request_id, result)
                        if model_call.tool_name != EXPAND_TOOL_NAME and result.status == "success":
                            # Expansion only changes the model's tool projection. A successful
                            # ordinary tool call is the generic evidence that the model acted on
                            # the outstanding recovery obligation.
                            recovery_pending = False
                        elif result.error and result.error.model_recovery_required:
                            recovery_pending = True
                    self._emit(request_id, "model.resumed", {})
        except asyncio.CancelledError as error:
            self._store.complete_request(request_id, "cancelled")
            self._emit(request_id, "request.cancelled", {})
            raise RequestCancelled("Request cancelled.") from error
        except ModelBackendError as error:
            self._store.complete_request(request_id, "failed", str(error))
            self._emit(
                request_id,
                "request.failed",
                {"message": str(error), "model_error_kind": error.kind.value},
            )
            raise RequestFailed(str(error)) from error
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
    ) -> tuple[ModelTurn, ModelUsage | None, tuple[SourceRef, ...]]:
        completed_turn: ModelTurn | None = None
        completed_usage: ModelUsage | None = None
        context = self._context_builder.build_with_metadata(
            session_id, scope.project_id, project_id_is_resolved=True
        )
        recovery_message = (
            (ContextMessage(role="system", content=_RECOVERY_DECISION_INSTRUCTIONS),)
            if recovery_decision
            else ()
        )
        async for event in self._backend.stream(
            (
                *context.messages,
                *recovery_message,
                ContextMessage(role="system", content=tool_exposure.catalog),
            ),
            tool_exposure.model_tools,
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
            raise RequestFailed("Assistant cited an unavailable source.")
        attachment_ids = self._store.session_attachment_ids(scope.session_id)
        for source_ref_id in turn.assistant.citation_source_ref_ids:
            source = sources_by_id[source_ref_id]
            if source.source_kind == "internet" and source.document_id is None and source.url:
                continue
            if source.source_kind in {"linux", "grafana", "zabbix"} and source.document_id is None:
                continue
            if source.document_id is None:
                raise RequestFailed("Assistant cited an unavailable source.")
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
                raise RequestFailed("Assistant cited an unavailable source.")

    @staticmethod
    def _ensure_not_cancelled(cancellation: asyncio.Event) -> None:
        if cancellation.is_set():
            raise asyncio.CancelledError
