"""One model-driven Chat runtime and its canonical tool loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from orion.contracts import RuntimeScope, ToolResult
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings
from orion.persistence.sqlite import SQLiteStore
from orion.runtime.context_builder import ContextBuilder
from orion.tools.registry import ToolRegistry
from orion.tools.runner import ToolRunner


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
    ) -> None:
        self._store = store
        self._backend = backend
        self._registry = registry
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
                # The stream is the public request boundary. Include the opaque request
                # identifier so an SSE client can use cancellation and event history.
                self._emit(
                    request_id,
                    "request.started",
                    {"request_id": request_id, "session_id": session_id},
                )
                settings = self._settings()
                while True:
                    self._ensure_not_cancelled(cancellation)
                    self._emit(request_id, "model.started", {})
                    turn = await self._backend.complete(
                        self._context_builder.build(session_id),
                        self._registry.definitions(),
                        settings,
                        cancellation,
                    )
                    self._ensure_not_cancelled(cancellation)
                    self._emit(
                        request_id, "model.completed", {"tool_call_count": len(turn.tool_calls)}
                    )
                    self._store.append_timeline(
                        session_id,
                        request_id,
                        "assistant_message",
                        {
                            "content": turn.assistant.content if turn.assistant is not None else "",
                            "tool_calls": [
                                call.model_dump(mode="json") for call in turn.tool_calls
                            ],
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
                    scope = RuntimeScope(session_id=session_id, project_id=None, attachment_ids=())
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

    @staticmethod
    def _ensure_not_cancelled(cancellation: asyncio.Event) -> None:
        if cancellation.is_set():
            raise asyncio.CancelledError
