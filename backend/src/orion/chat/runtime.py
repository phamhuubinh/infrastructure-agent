"""One model-driven Chat runtime and its streaming canonical tool loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from orion.access import LocalAccessAdapter
from orion.chat.context_builder import ContextBuilder
from orion.contracts import (
    AssistantDelta,
    ModelTurn,
    ModelTurnCompleted,
    RuntimeScope,
    TimelineItem,
    ToolResult,
    citations_are_visible,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.registry import ToolRegistry
from orion.tool_runtime.runner import ToolRunner


class RequestCancelled(RuntimeError):
    """The user cancelled an in-flight model/tool request."""


class RequestFailed(RuntimeError):
    """A model failure exposed at the request boundary."""


@dataclass(frozen=True)
class RequestOutcome:
    request_id: str
    assistant_content: str


class ChatRuntime:
    def __init__(
        self,
        store: SQLiteStore,
        backend: ModelBackend,
        registry: ToolRegistry,
        access: LocalAccessAdapter,
    ) -> None:
        self._store = store
        self._backend = backend
        self._registry = registry
        self._access = access
        self._runner = ToolRunner(registry)
        self._context_builder = ContextBuilder(store)
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
                while True:
                    self._ensure_not_cancelled(cancellation)
                    self._emit(request_id, "model.started", {})
                    turn = await self._stream_turn(session_id, request_id, settings, cancellation)
                    self._ensure_not_cancelled(cancellation)
                    self._emit(
                        request_id, "model.completed", {"tool_call_count": len(turn.tool_calls)}
                    )
                    self._validate_citations(turn, session_id)
                    assistant_item = self._persist_assistant_turn(session_id, request_id, turn)
                    if turn.assistant is not None:
                        self._emit(
                            request_id,
                            "assistant.message",
                            {
                                "item": assistant_item.model_dump(mode="json"),
                                "content": turn.assistant.content,
                            },
                        )
                    if not turn.tool_calls:
                        if turn.assistant is None:
                            raise RuntimeError("Model returned an invalid terminal turn.")
                        self._store.complete_request(request_id, "completed")
                        self._emit(request_id, "request.completed", {})
                        return RequestOutcome(
                            request_id=request_id, assistant_content=turn.assistant.content
                        )
                    for model_call in turn.tool_calls:
                        self._ensure_not_cancelled(cancellation)
                        self._store.append_timeline(
                            session_id,
                            request_id,
                            "tool_call",
                            {"arguments": model_call.arguments},
                            call_id=model_call.call_id,
                            tool_name=model_call.tool_name,
                        )
                        self._emit(
                            request_id,
                            "tool.started",
                            {"call_id": model_call.call_id, "tool_name": model_call.tool_name},
                        )
                        result = self._runner.run(model_call, scope)
                        self._persist_tool_result(session_id, request_id, result)
                    self._emit(request_id, "model.resumed", {})
        except asyncio.CancelledError as error:
            self._store.complete_request(request_id, "cancelled")
            self._emit(request_id, "request.cancelled", {})
            raise RequestCancelled("Request cancelled.") from error
        except ModelBackendError as error:
            self._store.complete_request(request_id, "failed", str(error))
            self._emit(request_id, "request.failed", {"message": str(error)})
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
        cancellation: asyncio.Event,
    ) -> ModelTurn:
        completed_turn: ModelTurn | None = None
        async for event in self._backend.stream(
            self._context_builder.build(session_id),
            self._registry.definitions(),
            settings,
            cancellation,
        ):
            self._ensure_not_cancelled(cancellation)
            if isinstance(event, AssistantDelta):
                self._emit(request_id, "assistant.delta", {"content": event.content})
            elif isinstance(event, ModelTurnCompleted):
                completed_turn = event.turn
        if completed_turn is None:
            raise ModelBackendError("Model stream ended without a completed turn.")
        return completed_turn

    def _runtime_scope(self, session_id: str) -> RuntimeScope:
        identity = self._store.session_identity(session_id)
        if identity is None:
            raise RequestFailed("Session is unavailable.")
        principal = self._access.principal_for_session(
            identity["principal_id"], identity["workspace_id"]
        )
        return RuntimeScope(
            session_id=session_id,
            project_id=None,
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
        self, session_id: str, request_id: str, turn: ModelTurn
    ) -> TimelineItem:
        return self._store.append_timeline(
            session_id,
            request_id,
            "assistant_message",
            {
                "content": turn.assistant.content if turn.assistant is not None else "",
                "citation_source_ref_ids": (
                    list(turn.assistant.citation_source_ref_ids)
                    if turn.assistant is not None
                    else []
                ),
                "tool_calls": [call.model_dump(mode="json") for call in turn.tool_calls],
            },
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
        self._emit(
            request_id,
            event_type,
            {"call_id": result.call_id, "tool_name": result.tool_name, "status": result.status},
        )

    def _emit(self, request_id: str, event_type: str, payload: dict[str, object]) -> None:
        self._store.emit_event(request_id, event_type, payload)

    def _fail_unexpected(self, request_id: str) -> None:
        self._store.complete_request(request_id, "failed", "Request failed unexpectedly.")
        self._emit(request_id, "request.failed", {"message": "Request failed unexpectedly."})

    def _validate_citations(self, turn: ModelTurn, session_id: str) -> None:
        if turn.assistant is None or not turn.assistant.citation_source_ref_ids:
            return
        visible_source_ref_ids: set[str] = set()
        attachment_ids = self._store.session_attachment_ids(session_id)
        for item in self._store.timeline(session_id):
            if item.kind != "tool_result":
                continue
            result = ToolResult.model_validate(item.payload["result"])
            for source in result.sources:
                if source.document_id is None:
                    continue
                document = self._store.document(source.document_id)
                if (
                    document is not None
                    and document["session_id"] == session_id
                    and document["attachment_id"] in attachment_ids
                    and document["status"] == "ready"
                ):
                    visible_source_ref_ids.add(source.source_ref_id)
        if not citations_are_visible(
            turn.assistant.citation_source_ref_ids, visible_source_ref_ids
        ):
            raise RequestFailed("Assistant cited an unavailable source.")

    @staticmethod
    def _ensure_not_cancelled(cancellation: asyncio.Event) -> None:
        if cancellation.is_set():
            raise asyncio.CancelledError
