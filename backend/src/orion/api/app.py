"""HTTP/SSE boundary; concrete dependency composition lives in bootstrap."""

from __future__ import annotations

import asyncio
import json
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from orion.access import LocalAccessAdapter
from orion.access.remote import COOKIE_NAME, SESSION_SECONDS, BrowserSessions, RemoteAccessConfig
from orion.api.scheduler import install_scheduler_routes
from orion.bootstrap import (
    OrionApplication,
    application_context,
    build_application,
    prepare_mcp_manager,
)
from orion.chat.runtime import (
    ChatRuntime,
    CitationValidationFailed,
    RequestCancelled,
    RequestFailed,
)
from orion.contracts import RuntimeScope
from orion.models.backend import ModelBackend, ReasoningMode
from orion.paths import (
    ORION_HEALTH_IDENTITY,
    PACKAGED_UI_SHELL,
    document_upload_limit,
    packaged_ui_directory,
)
from orion.persistence.sqlite import SQLiteStore
from orion.security import redact_text, safe_endpoint
from orion.tool_runtime.mutation_authorization import MutationMode

_UPLOAD_CHUNK_BYTES = 64 * 1024
_PUBLIC_ROOT_STATIC = {
    "_shell.html",
    "favicon.ico",
    "orion-icon.png",
    "orion-icon-light.png",
    "orion-icon-dark.png",
}


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Explicit API inventory. The test compares this set with every registered API route.
PUBLIC_API_ROUTES = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/session"),
}
PROTECTED_API_ROUTES = {
    ("GET", "/api/mcp/servers"),
    ("POST", "/api/scheduler/tasks"),
    ("GET", "/api/scheduler/tasks"),
    ("GET", "/api/scheduler/tasks/{task_id}"),
    ("POST", "/api/scheduler/tasks/{task_id}/pause"),
    ("POST", "/api/scheduler/tasks/{task_id}/resume"),
    ("DELETE", "/api/scheduler/tasks/{task_id}"),
    ("GET", "/api/scheduler/tasks/{task_id}/history"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/models"),
    ("POST", "/api/models"),
    ("PUT", "/api/models/{model_config_id}"),
    ("POST", "/api/models/{model_config_id}/activate"),
    ("DELETE", "/api/models/{model_config_id}"),
    ("POST", "/api/sessions"),
    ("GET", "/api/sessions"),
    ("GET", "/api/sessions/{session_id}"),
    ("PATCH", "/api/sessions/{session_id}/mutation-mode"),
    ("PATCH", "/api/sessions/{session_id}"),
    ("DELETE", "/api/sessions/{session_id}"),
    ("GET", "/api/projects"),
    ("POST", "/api/projects"),
    ("GET", "/api/projects/{project_id}"),
    ("PUT", "/api/projects/{project_id}"),
    ("DELETE", "/api/projects/{project_id}"),
    ("POST", "/api/projects/{project_id}/sessions"),
    ("POST", "/api/projects/{project_id}/documents"),
    ("GET", "/api/projects/{project_id}/documents"),
    ("GET", "/api/projects/{project_id}/documents/{document_id}"),
    ("DELETE", "/api/projects/{project_id}/documents/{document_id}"),
    ("GET", "/api/sessions/{session_id}/timeline"),
    ("POST", "/api/sessions/{session_id}/attachments"),
    ("GET", "/api/sessions/{session_id}/documents/{document_id}"),
    ("DELETE", "/api/sessions/{session_id}/documents/{document_id}"),
    ("POST", "/api/sessions/{session_id}/messages"),
    ("POST", "/api/sessions/{session_id}/messages/stream"),
    ("GET", "/api/requests/{request_id}/events"),
    ("GET", "/api/requests/{request_id}/diagnostics"),
    ("POST", "/api/requests/{request_id}/cancel"),
    ("POST", "/api/sessions/{session_id}/requests/{request_id}/tool-authorizations/{call_id}"),
}


class RemoteAccessMiddleware:
    """Pure ASGI boundary so authenticated SSE responses are never interrupted."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        routes_app: FastAPI,
        sessions: BrowserSessions,
        public_origin: str,
    ) -> None:
        self._app = app
        self._routes_app = routes_app
        self._sessions = sessions
        self._public_origin = public_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        request = Request(scope, receive)
        path, method = request.url.path, request.method

        async def send_remote(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                headers = [
                    *message.get("headers", []),
                    (b"content-security-policy", b"frame-ancestors 'none'"),
                    (b"x-frame-options", b"DENY"),
                ]
                if path.startswith("/api/"):
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        if (
            method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("origin") != self._public_origin
        ):
            await Response(status_code=403)(scope, receive, send_remote)
            return
        if path.startswith("/api/"):
            classification = None
            for route in self._routes_app.routes:
                if isinstance(route, APIRoute) and route.path.startswith("/api/"):
                    match, _ = route.matches(scope)
                    if match == Match.FULL:
                        classification = (method, route.path)
                        break
            if classification not in PUBLIC_API_ROUTES:
                if classification not in PROTECTED_API_ROUTES:
                    await Response(status_code=404)(scope, receive, send_remote)
                    return
                if self._sessions.expiry(request.cookies.get(COOKIE_NAME)) is None:
                    await Response(status_code=401)(scope, receive, send_remote)
                    return
        elif path in {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}:
            if self._sessions.expiry(request.cookies.get(COOKIE_NAME)) is None:
                await Response(status_code=401)(scope, receive, send_remote)
                return

        await self._app(scope, receive, send_remote)


class ModelConfigInput(StrictRequest):
    provider_type: str = Field(pattern=r"^openai_compatible$")
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key: str | None = None
    reasoning_mode: ReasoningMode = ReasoningMode.AUTO


class ModelConfigView(BaseModel):
    model_config_id: str
    provider_type: str
    base_url: str
    model_id: str
    reasoning_mode: ReasoningMode
    is_active: bool


class SubmitMessage(StrictRequest):
    content: str = Field(min_length=1)


class SessionView(BaseModel):
    session_id: str
    project_id: str | None = None
    custom_title: str | None = None
    mutation_mode: MutationMode = MutationMode.READ_ONLY


class SessionSummaryView(SessionView):
    title: str
    created_at: str
    last_activity_at: str


class SessionTitleUpdate(StrictRequest):
    title: str = Field(max_length=120)


class SessionMutationModeUpdate(StrictRequest):
    mutation_mode: MutationMode


class ToolAuthorizationDecision(StrictRequest):
    decision: str = Field(pattern=r"^(allow|deny)$")


class SessionTitleView(SessionView):
    title: str


class ProjectInput(StrictRequest):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    instructions: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectView(ProjectInput):
    project_id: str
    created_at: str
    updated_at: str


class AssistantResponse(BaseModel):
    request_id: str
    assistant_content: str
    status: str


class AttachmentView(BaseModel):
    document: dict[str, object]
    attachment_id: str
    status: str
    error_message: str | None = None


def create_app(
    database_path: Path | None = None,
    backend: ModelBackend | None = None,
    application: OrionApplication | None = None,
    ui_directory: Path | None = None,
    remote_config: RemoteAccessConfig | None = None,
) -> FastAPI:
    """Adapt bootstrap-owned application dependencies to the public HTTP API."""
    remote = remote_config or RemoteAccessConfig.from_environment()
    manager = prepare_mcp_manager() if application is None else None
    assembled = application or (
        build_application(database_path, backend) if manager is None else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with application_context(
            database_path, backend, application=assembled, mcp_manager=manager
        ) as running:
            if assembled is None:
                _install_application_routes(app, running, ui_directory, sessions, remote)
            running.scheduler_engine.start()
            try:
                yield
            finally:
                await running.scheduler_engine.stop()

    app = FastAPI(title="Orion", version="0.1.0", lifespan=lifespan)
    sessions = (
        BrowserSessions(remote.password_hash) if remote.enabled and remote.password_hash else None
    )
    app.state.browser_sessions = sessions
    if remote.enabled:
        assert sessions is not None and remote.public_origin is not None
        app.add_middleware(
            RemoteAccessMiddleware,
            routes_app=app,
            sessions=sessions,
            public_origin=remote.public_origin,
        )
    if assembled is not None:
        _install_application_routes(app, assembled, ui_directory, sessions, remote)
    return app


def _install_application_routes(
    app: FastAPI,
    assembled: OrionApplication,
    ui_directory: Path | None,
    sessions: BrowserSessions | None,
    remote: RemoteAccessConfig,
) -> None:
    """Install boundary adapters only after the single canonical snapshot is ready."""
    store, runtime = assembled.store, assembled.runtime
    max_upload_bytes = document_upload_limit()
    app.state.application = assembled
    install_scheduler_routes(
        app,
        assembled.scheduler,
        lambda session_id: _session_scope(store, assembled.access, session_id),
    )

    @app.get("/api/mcp/servers")
    async def mcp_servers() -> list[dict[str, object]]:
        return assembled.mcp.status() if assembled.mcp else []

    def model_config_view(config: dict[str, str | int | None]) -> ModelConfigView:
        return ModelConfigView(
            model_config_id=str(config["model_config_id"]),
            provider_type=str(config["provider_type"]),
            base_url=safe_endpoint(str(config["base_url"])),
            model_id=redact_text(str(config["model_id"])),
            reasoning_mode=ReasoningMode(str(config["reasoning_mode"])),
            is_active=bool(config["is_active"]),
        )

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "identity": ORION_HEALTH_IDENTITY,
        }

    @app.post(
        "/api/auth/login",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"password": {"type": "string", "format": "password"}},
                            "required": ["password"],
                            "additionalProperties": False,
                        }
                    }
                },
            }
        },
    )
    async def login(request: Request) -> Response:
        if sessions is None:
            raise HTTPException(status_code=404, detail="Not found.")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 2048:
                raise HTTPException(status_code=400, detail="Invalid login request.")
            body.extend(chunk)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid login request.") from None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"password"}
            or not isinstance(payload["password"], str)
            or not 1 <= len(payload["password"]) <= 1024
        ):
            raise HTTPException(status_code=400, detail="Invalid login request.")
        result = await asyncio.to_thread(sessions.login, payload["password"])
        if result is None:
            raise HTTPException(status_code=401, detail="Invalid credentials.")
        token, expiry = result
        response = Response(
            content=json.dumps({"authenticated": True, "expires_at": expiry}),
            media_type="application/json",
        )
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/auth/session")
    async def auth_session(request: Request) -> dict[str, object]:
        if sessions is None:
            return {"remote_access": False, "authenticated": True, "expires_at": None}
        expiry = sessions.expiry(request.cookies.get(COOKIE_NAME))
        return {"remote_access": True, "authenticated": expiry is not None, "expires_at": expiry}

    @app.post("/api/auth/logout")
    async def logout(request: Request) -> Response:
        if sessions is None:
            raise HTTPException(status_code=404, detail="Not found.")
        sessions.logout(request.cookies.get(COOKIE_NAME))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
        return response

    @app.get("/api/models", response_model=list[ModelConfigView])
    async def get_models() -> list[ModelConfigView]:
        return [model_config_view(config) for config in store.model_configs()]

    @app.post("/api/models", response_model=ModelConfigView, status_code=201)
    async def configure_model(config: ModelConfigInput) -> ModelConfigView:
        config_id = store.create_model_config(
            config.provider_type,
            config.base_url,
            config.model_id,
            config.api_key.strip() if config.api_key and config.api_key.strip() else None,
            config.reasoning_mode.value,
        )
        created = store.model_config(config_id)
        assert created is not None
        return model_config_view(created)

    @app.put("/api/models/{model_config_id}", response_model=ModelConfigView)
    async def update_model(model_config_id: str, config: ModelConfigInput) -> ModelConfigView:
        updated = store.update_model_config(
            model_config_id,
            config.provider_type,
            config.base_url,
            config.model_id,
            config.api_key.strip() if config.api_key and config.api_key.strip() else None,
            (config.reasoning_mode.value if "reasoning_mode" in config.model_fields_set else None),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Model configuration not found.")
        stored = store.model_config(model_config_id)
        assert stored is not None
        return model_config_view(stored)

    @app.post("/api/models/{model_config_id}/activate", response_model=ModelConfigView)
    async def activate_model(model_config_id: str) -> ModelConfigView:
        if not store.activate_model_config(model_config_id):
            raise HTTPException(status_code=404, detail="Model configuration not found.")
        stored = store.model_config(model_config_id)
        assert stored is not None
        return model_config_view(stored)

    @app.delete("/api/models/{model_config_id}", status_code=204)
    async def delete_model(model_config_id: str) -> Response:
        result = store.delete_model_config(model_config_id)
        if result == "missing":
            raise HTTPException(status_code=404, detail="Model configuration not found.")
        if result == "active":
            raise HTTPException(
                status_code=409,
                detail="Select another model before deleting the active configuration.",
            )
        return Response(status_code=204)

    @app.post("/api/sessions", response_model=SessionView, status_code=201)
    async def create_session() -> SessionView:
        principal = assembled.access.current_principal()
        return SessionView(
            session_id=store.create_session(principal.principal_id, principal.workspace_id)
        )

    @app.get("/api/sessions", response_model=list[SessionSummaryView])
    async def list_sessions() -> list[SessionSummaryView]:
        principal = assembled.access.current_principal()
        return [
            SessionSummaryView.model_validate(summary)
            for summary in store.session_summaries(principal.principal_id, principal.workspace_id)
        ]

    @app.get("/api/sessions/{session_id}", response_model=SessionView)
    async def get_session(session_id: str) -> SessionView:
        identity = _require_session(store, assembled.access, session_id)
        return SessionView(
            session_id=session_id,
            project_id=identity["project_id"],
            custom_title=identity["custom_title"],
            mutation_mode=MutationMode(str(identity["mutation_mode"])),
        )

    @app.patch("/api/sessions/{session_id}/mutation-mode", response_model=SessionView)
    async def set_mutation_mode(session_id: str, update: SessionMutationModeUpdate) -> SessionView:
        identity = _require_session(store, assembled.access, session_id)
        try:
            store.set_session_mutation_mode(session_id, update.mutation_mode)
        except RuntimeError as error:
            if str(error) == "active_request":
                raise HTTPException(
                    status_code=409, detail="Finish or cancel the active request first."
                ) from error
            raise
        return SessionView(
            session_id=session_id,
            project_id=identity["project_id"],
            custom_title=identity["custom_title"],
            mutation_mode=update.mutation_mode,
        )

    @app.patch("/api/sessions/{session_id}", response_model=SessionTitleView)
    async def rename_session(session_id: str, update: SessionTitleUpdate) -> SessionTitleView:
        identity = _require_session(store, assembled.access, session_id)
        title = update.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Conversation title cannot be empty.")
        if not store.rename_session(session_id, title):
            raise HTTPException(status_code=404, detail="Session not found.")
        return SessionTitleView(
            session_id=session_id,
            project_id=identity["project_id"],
            custom_title=title,
            mutation_mode=MutationMode(str(identity["mutation_mode"])),
            title=title,
        )

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str) -> Response:
        _require_session(store, assembled.access, session_id)
        try:
            blob_ids = store.delete_session(session_id)
        except RuntimeError as error:
            if str(error) == "active_request":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The active request must finish or be cancelled before deleting this "
                        "conversation."
                    ),
                ) from error
            raise
        if blob_ids is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        assembled.knowledge.delete_blobs(blob_ids)
        return Response(status_code=204)

    @app.get("/api/projects", response_model=list[ProjectView])
    async def list_projects() -> list[ProjectView]:
        return [ProjectView.model_validate(project) for project in assembled.projects.list()]

    @app.post("/api/projects", response_model=ProjectView, status_code=201)
    async def create_project(project: ProjectInput) -> ProjectView:
        return ProjectView.model_validate(
            assembled.projects.create(
                project.name, project.description, project.instructions, project.metadata
            )
        )

    @app.get("/api/projects/{project_id}", response_model=ProjectView)
    async def get_project(project_id: str) -> ProjectView:
        project = assembled.projects.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return ProjectView.model_validate(project)

    @app.put("/api/projects/{project_id}", response_model=ProjectView)
    async def update_project(project_id: str, project: ProjectInput) -> ProjectView:
        updated = assembled.projects.update(
            project_id, project.name, project.description, project.instructions, project.metadata
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return ProjectView.model_validate(updated)

    @app.delete("/api/projects/{project_id}", status_code=204)
    async def delete_project(project_id: str) -> Response:
        try:
            blob_ids = assembled.projects.delete(project_id)
        except RuntimeError as error:
            if str(error) == "active_request":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The active Project conversation must finish or be cancelled before "
                        "deleting this Project."
                    ),
                ) from error
            raise
        if blob_ids is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        assembled.knowledge.delete_blobs(blob_ids)
        return Response(status_code=204)

    @app.post("/api/projects/{project_id}/sessions", response_model=SessionView, status_code=201)
    async def create_project_session(project_id: str) -> SessionView:
        principal = assembled.access.current_principal()
        try:
            session_id = assembled.projects.create_session(
                project_id, principal.principal_id, principal.workspace_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Project not found.") from error
        return SessionView(session_id=session_id, project_id=project_id)

    @app.post(
        "/api/projects/{project_id}/documents", response_model=AttachmentView, status_code=201
    )
    async def attach_project_document(
        project_id: str, file: Annotated[UploadFile, File()]
    ) -> AttachmentView:
        if assembled.projects.get(project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        name, content, media_type = await _read_document_upload(file, max_upload_bytes)
        uploaded = assembled.knowledge.attach_project(project_id, name, content, media_type)
        return AttachmentView(
            document=uploaded.document.model_dump(mode="json"),
            attachment_id=uploaded.attachment_id,
            status=uploaded.status,
            error_message=uploaded.error_message,
        )

    @app.get("/api/projects/{project_id}/documents")
    async def project_documents(project_id: str) -> list[dict[str, object]]:
        scope = _project_scope(store, assembled.access, project_id)
        statuses: list[dict[str, object]] = []
        for document in assembled.knowledge.list_project_documents(project_id):
            status = assembled.knowledge.document_status(document.document_id, scope)
            if status is not None:
                statuses.append(status)
        return statuses

    @app.get("/api/projects/{project_id}/documents/{document_id}")
    async def project_document_status(project_id: str, document_id: str) -> dict[str, object]:
        scope = _project_scope(store, assembled.access, project_id)
        status = assembled.knowledge.document_status(document_id, scope)
        if status is None or status["document"]["source"]["kind"] != "project":
            raise HTTPException(status_code=404, detail="Document not found.")
        return status

    @app.delete("/api/projects/{project_id}/documents/{document_id}")
    async def delete_project_document(project_id: str, document_id: str) -> dict[str, str]:
        scope = _project_scope(store, assembled.access, project_id)
        try:
            deleted = assembled.knowledge.delete(document_id, scope)
        except PermissionError as error:
            raise HTTPException(status_code=404, detail="Document not found.") from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"status": "deleted"}

    @app.get("/api/sessions/{session_id}/timeline")
    async def get_timeline(session_id: str) -> list[dict[str, object]]:
        _require_session(store, assembled.access, session_id)
        return [item.model_dump(mode="json") for item in store.timeline(session_id)]

    @app.post(
        "/api/sessions/{session_id}/attachments", response_model=AttachmentView, status_code=201
    )
    async def attach_document(
        session_id: str, file: Annotated[UploadFile, File()]
    ) -> AttachmentView:
        _require_session(store, assembled.access, session_id)
        name, content, media_type = await _read_document_upload(file, max_upload_bytes)
        uploaded = assembled.knowledge.attach(session_id, name, content, media_type)
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
        identity = _require_session(store, assembled.access, session_id)
        if identity["mutation_mode"] == MutationMode.CONFIRM.value:
            raise HTTPException(
                status_code=409,
                detail="Confirm mode requires the streaming message endpoint so the caller can "
                "resolve a pending mutation.",
            )
        try:
            outcome = await runtime.submit(session_id, message.content)
        except RequestCancelled as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except CitationValidationFailed as error:
            raise HTTPException(
                status_code=502, detail=CitationValidationFailed.public_message
            ) from error
        except RequestFailed as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return AssistantResponse(
            request_id=outcome.request_id,
            assistant_content=outcome.assistant_content,
            status=outcome.status,
        )

    @app.post("/api/sessions/{session_id}/messages/stream")
    async def stream_message(session_id: str, message: SubmitMessage) -> StreamingResponse:
        _require_session(store, assembled.access, session_id)
        request_id = runtime.begin(session_id, message.content)
        task = asyncio.create_task(runtime.run(session_id, request_id))
        return StreamingResponse(
            _sse_events(store, runtime, request_id, task), media_type="text/event-stream"
        )

    @app.get("/api/requests/{request_id}/events")
    async def request_events(request_id: str) -> list[dict[str, object]]:
        request = store.request(request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found.")
        _require_session(store, assembled.access, str(request["session_id"]))
        return store.events(request_id)

    @app.get("/api/requests/{request_id}/diagnostics")
    async def request_diagnostics(request_id: str) -> dict[str, object]:
        request = store.request(request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found.")
        _require_session(store, assembled.access, str(request["session_id"]))
        diagnostic = runtime.diagnostics(request_id)
        if diagnostic is None:
            raise HTTPException(status_code=404, detail="Runtime diagnostics are disabled.")
        return diagnostic

    @app.post("/api/requests/{request_id}/cancel")
    async def cancel_request(request_id: str) -> dict[str, str]:
        request = store.request(request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found.")
        _require_session(store, assembled.access, str(request["session_id"]))
        if not runtime.cancel(request_id):
            raise HTTPException(status_code=409, detail="Request is no longer running.")
        return {"status": "cancellation_requested"}

    @app.post("/api/sessions/{session_id}/requests/{request_id}/tool-authorizations/{call_id}")
    async def resolve_tool_authorization(
        session_id: str,
        request_id: str,
        call_id: str,
        decision: ToolAuthorizationDecision,
    ) -> dict[str, str]:
        _require_session(store, assembled.access, session_id)
        request = store.request(request_id)
        if request is None or request["session_id"] != session_id:
            raise HTTPException(status_code=404, detail="Request not found in this conversation.")
        if not runtime.resolve_authorization(
            session_id, request_id, call_id, decision.decision == "allow"
        ):
            raise HTTPException(status_code=409, detail="Authorization is unavailable or resolved.")
        return {"status": "allowed" if decision.decision == "allow" else "denied"}

    frontend = (ui_directory or packaged_ui_directory()).expanduser().resolve()

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_application(frontend_path: str) -> Response:
        """Serve packaged client assets and let the browser router own UI routes.

        API paths stay inside the API namespace even when no endpoint matches;
        they must never receive the SPA shell.
        """
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        requested = (frontend / frontend_path).resolve()
        if requested.is_relative_to(frontend) and requested.is_file():
            if remote.enabled and not (
                frontend_path in _PUBLIC_ROOT_STATIC
                or requested.is_relative_to(frontend / "assets")
            ):
                raise HTTPException(status_code=404, detail="Not found.")
            return _static_file_response(requested)
        shell = frontend / PACKAGED_UI_SHELL
        if not shell.is_file():
            raise HTTPException(
                status_code=503,
                detail="Orion's packaged UI is missing. Run ./install.sh to build it.",
            )
        return _static_file_response(shell)


async def _read_document_upload(
    upload: UploadFile, maximum_bytes: int
) -> tuple[str, bytes, str | None]:
    raw_name = (upload.filename or "").replace("\\", "/")
    name = raw_name.rsplit("/", 1)[-1].strip()
    if not name:
        await upload.close()
        raise HTTPException(status_code=422, detail="Document filename is required.")
    content = bytearray()
    try:
        while chunk := await upload.read(_UPLOAD_CHUNK_BYTES):
            if len(content) + len(chunk) > maximum_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Document exceeds the configured {maximum_bytes}-byte upload limit.",
                )
            content.extend(chunk)
    finally:
        await upload.close()
    return name, bytes(content), upload.content_type


def _static_file_response(path: Path) -> StreamingResponse:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return StreamingResponse(
        _file_chunks(path),
        media_type=media_type,
        headers={"Content-Length": str(path.stat().st_size)},
    )


async def _file_chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as file:
        while chunk := file.read(64 * 1024):
            yield chunk


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


def _require_session(
    store: SQLiteStore, access: LocalAccessAdapter, session_id: str
) -> dict[str, str | None]:
    identity = store.session_identity(session_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        access.principal_for_session(str(identity["principal_id"]), str(identity["workspace_id"]))
    except PermissionError as error:
        raise HTTPException(status_code=404, detail="Session not found.") from error
    return identity


def _session_scope(store: SQLiteStore, access: LocalAccessAdapter, session_id: str) -> RuntimeScope:
    identity = _require_session(store, access, session_id)
    principal = access.current_principal()
    return RuntimeScope(
        session_id=session_id,
        project_id=identity["project_id"],
        attachment_ids=store.session_attachment_ids(session_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
    )


def _project_scope(store: SQLiteStore, access: LocalAccessAdapter, project_id: str) -> RuntimeScope:
    if store.project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    principal = access.current_principal()
    return RuntimeScope(
        session_id="project-document-management",
        project_id=project_id,
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
    )
