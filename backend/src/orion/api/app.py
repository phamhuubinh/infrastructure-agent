"""HTTP/SSE boundary; concrete dependency composition lives in bootstrap."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from orion.access import LocalAccessAdapter
from orion.bootstrap import OrionApplication, build_application
from orion.chat.runtime import ChatRuntime, RequestCancelled, RequestFailed
from orion.contracts import RuntimeScope
from orion.models.backend import ModelBackend
from orion.persistence.sqlite import SQLiteStore


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelConfigInput(StrictRequest):
    provider_type: str = Field(pattern=r"^openai_compatible$")
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key: str | None = None


class ModelConfigView(BaseModel):
    model_config_id: str
    provider_type: str
    base_url: str
    model_id: str


class SubmitMessage(StrictRequest):
    content: str = Field(min_length=1)


class SessionView(BaseModel):
    session_id: str


class AssistantResponse(BaseModel):
    request_id: str
    assistant_content: str


class AttachmentInput(StrictRequest):
    name: str = Field(min_length=1)
    content: str
    media_type: str | None = "text/plain"


class AttachmentView(BaseModel):
    document: dict[str, object]
    attachment_id: str
    status: str
    error_message: str | None = None


def create_app(
    database_path: Path | None = None,
    backend: ModelBackend | None = None,
    application: OrionApplication | None = None,
) -> FastAPI:
    """Adapt bootstrap-owned application dependencies to the public HTTP API."""
    assembled = application or build_application(database_path, backend)
    store, runtime = assembled.store, assembled.runtime
    app = FastAPI(title="Orion", version="0.1.0")
    app.state.application = assembled

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/models", response_model=list[ModelConfigView])
    async def get_models() -> list[ModelConfigView]:
        active = store.active_model_config()
        return [ModelConfigView.model_validate(active)] if active else []

    @app.post("/api/models", response_model=ModelConfigView, status_code=201)
    async def configure_model(config: ModelConfigInput) -> ModelConfigView:
        config_id = store.upsert_model_config(
            config.provider_type, config.base_url, config.model_id, config.api_key
        )
        return ModelConfigView(
            model_config_id=config_id,
            provider_type=config.provider_type,
            base_url=config.base_url.rstrip("/"),
            model_id=config.model_id,
        )

    @app.post("/api/sessions", response_model=SessionView, status_code=201)
    async def create_session() -> SessionView:
        principal = assembled.access.current_principal()
        return SessionView(
            session_id=store.create_session(principal.principal_id, principal.workspace_id)
        )

    @app.get("/api/sessions/{session_id}/timeline")
    async def get_timeline(session_id: str) -> list[dict[str, object]]:
        _require_session(store, session_id)
        return [item.model_dump(mode="json") for item in store.timeline(session_id)]

    @app.post(
        "/api/sessions/{session_id}/attachments", response_model=AttachmentView, status_code=201
    )
    async def attach_document(session_id: str, attachment: AttachmentInput) -> AttachmentView:
        _require_session(store, session_id)
        uploaded = assembled.knowledge.attach(
            session_id, attachment.name, attachment.content.encode(), attachment.media_type
        )
        return AttachmentView(
            document=uploaded.document.model_dump(mode="json"),
            attachment_id=uploaded.attachment_id,
            status=uploaded.status,
            error_message=uploaded.error_message,
        )

    @app.get("/api/sessions/{session_id}/documents/{document_id}")
    async def document_status(session_id: str, document_id: str) -> dict[str, object]:
        scope = _session_scope(store, assembled.access, session_id)
        status = assembled.knowledge.document_status(document_id, scope)
        if status is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return status

    @app.delete("/api/sessions/{session_id}/documents/{document_id}")
    async def delete_document(session_id: str, document_id: str) -> dict[str, str]:
        scope = _session_scope(store, assembled.access, session_id)
        try:
            deleted = assembled.knowledge.delete(document_id, scope)
        except PermissionError as error:
            raise HTTPException(status_code=404, detail="Document not found.") from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"status": "deleted"}

    @app.post("/api/sessions/{session_id}/messages", response_model=AssistantResponse)
    async def submit_message(session_id: str, message: SubmitMessage) -> AssistantResponse:
        _require_session(store, session_id)
        try:
            outcome = await runtime.submit(session_id, message.content)
        except RequestCancelled as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except RequestFailed as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return AssistantResponse(
            request_id=outcome.request_id, assistant_content=outcome.assistant_content
        )

    @app.post("/api/sessions/{session_id}/messages/stream")
    async def stream_message(session_id: str, message: SubmitMessage) -> StreamingResponse:
        _require_session(store, session_id)
        request_id = runtime.begin(session_id, message.content)
        task = asyncio.create_task(runtime.run(session_id, request_id))
        return StreamingResponse(
            _sse_events(store, runtime, request_id, task), media_type="text/event-stream"
        )

    @app.get("/api/requests/{request_id}/events")
    async def request_events(request_id: str) -> list[dict[str, object]]:
        if store.request(request_id) is None:
            raise HTTPException(status_code=404, detail="Request not found.")
        return store.events(request_id)

    @app.post("/api/requests/{request_id}/cancel")
    async def cancel_request(request_id: str) -> dict[str, str]:
        if store.request(request_id) is None:
            raise HTTPException(status_code=404, detail="Request not found.")
        if not runtime.cancel(request_id):
            raise HTTPException(status_code=409, detail="Request is no longer running.")
        return {"status": "cancellation_requested"}

    return app


async def _sse_events(
    store: SQLiteStore, runtime: ChatRuntime, request_id: str, task: asyncio.Task[object]
) -> AsyncIterator[str]:
    cursor = 0
    try:
        while True:
            events = store.events(request_id)
            for event in events[cursor:]:
                yield f"data: {json.dumps(event)}\n\n"
            cursor = len(events)
            if task.done():
                try:
                    await task
                except (RequestCancelled, RequestFailed):
                    pass
                return
            await asyncio.sleep(0.01)
    finally:
        if not task.done():
            runtime.cancel(request_id)


def _require_session(store: SQLiteStore, session_id: str) -> None:
    if not store.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")


def _session_scope(store: SQLiteStore, access: LocalAccessAdapter, session_id: str) -> RuntimeScope:
    identity = store.session_identity(session_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        principal = access.principal_for_session(identity["principal_id"], identity["workspace_id"])
    except PermissionError as error:
        raise HTTPException(status_code=404, detail="Session not found.") from error
    return RuntimeScope(
        session_id=session_id,
        attachment_ids=store.session_attachment_ids(session_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
    )
