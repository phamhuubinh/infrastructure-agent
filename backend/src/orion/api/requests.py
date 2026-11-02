"""Admit once and resume bounded observation without replaying the model/tool loop."""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from orion.access.native import NativeAuthService
from orion.application.requests import RequestAdmissionError, RequestService
from orion.contracts import RuntimeScope
from orion.contracts.requests import AdmitRequest, RequestEventPage, RequestEventRecord, RequestView
from orion.security import redact_text

REQUEST_OWNER_ROUTES = {
    ("POST", "/api/sessions/{session_id}/requests"),
    ("POST", "/api/sessions/{session_id}/request-cancellations"),
    ("GET", "/api/requests/{request_id}"),
    ("GET", "/api/requests/{request_id}/event-page"),
    ("GET", "/api/requests/{request_id}/stream"),
}


def install_request_routes(
    app: FastAPI,
    service: RequestService,
    native: NativeAuthService,
    scope_for_session: Callable[[str], RuntimeScope],
    observer_active: Callable[[Request], bool] | None = None,
) -> None:
    def view(request_id: str) -> RequestView:
        row = service.store.request(request_id)
        if row is None:
            raise HTTPException(404, "Request not found")
        scope_for_session(row["session_id"])
        return RequestView.model_validate(
            {
                **row,
                "error_message": redact_text(row["error_message"])
                if row["error_message"]
                else None,
            }
        )

    def page(request_id: str, after: str | None, limit: int) -> RequestEventPage:
        current = view(request_id)
        try:
            events, more = service.store.request_event_page(request_id, after, limit)
        except ValueError:
            raise HTTPException(409, "Request event page unavailable") from None
        return RequestEventPage(
            events=[RequestEventRecord.model_validate(event) for event in events],
            has_more=more,
            next_cursor=events[-1]["event_id"] if events else after,
            status=current.status,
        )

    @app.post(
        "/api/sessions/{session_id}/requests",
        response_model=RequestView,
        status_code=202,
        openapi_extra={"x-orion-idempotency": "client_request_id"},
    )
    async def admit(session_id: str, body: AdmitRequest, response: Response) -> RequestView:
        scope = scope_for_session(session_id)
        try:
            identity, _ = service.admit(scope, body.content, str(body.client_request_id))
        except RequestAdmissionError as error:
            raise HTTPException(409, "Request admission unavailable: " + error.category) from None
        response.headers["Location"] = "/api/requests/" + identity
        response.headers["Cache-Control"] = "no-store"
        return view(identity)

    @app.post(
        "/api/sessions/{session_id}/request-cancellations",
        response_model=RequestView,
        status_code=202,
        openapi_extra={"x-orion-idempotency": "client_request_id"},
    )
    async def cancel_admission(
        session_id: str, body: AdmitRequest, response: Response
    ) -> RequestView:
        scope = scope_for_session(session_id)
        try:
            identity = service.cancel_admission(scope, body.content, str(body.client_request_id))
        except RequestAdmissionError as error:
            raise HTTPException(
                409, "Request cancellation unavailable: " + error.category
            ) from None
        response.headers["Cache-Control"] = "no-store"
        return view(identity)

    @app.get("/api/requests/{request_id}", response_model=RequestView)
    async def get_request(request_id: str, response: Response) -> RequestView:
        response.headers["Cache-Control"] = "no-store"
        return view(request_id)

    @app.get("/api/requests/{request_id}/event-page", response_model=RequestEventPage)
    async def events(
        request_id: str,
        response: Response,
        after: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=256)] = 64,
    ) -> RequestEventPage:
        response.headers["Cache-Control"] = "no-store"
        return page(request_id, str(after) if after else None, limit)

    @app.get(
        "/api/requests/{request_id}/stream",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
        openapi_extra={
            "parameters": [
                {
                    "name": "Last-Event-ID",
                    "in": "header",
                    "schema": {"type": "string", "format": "uuid"},
                }
            ]
        },
    )
    async def stream(
        request_id: str, request: Request, after: UUID | None = None
    ) -> StreamingResponse:
        cursor = str(after) if after else None
        resume = request.headers.get("last-event-id")
        if resume:
            try:
                resumed = str(UUID(resume))
            except ValueError:
                raise HTTPException(422, "Invalid observation cursor") from None
            if cursor is not None and cursor != resumed:
                raise HTTPException(409, "Conflicting observation cursors")
            cursor = resumed
        first = page(request_id, cursor, 64)

        async def observe() -> AsyncIterator[str]:
            current = first
            position = cursor
            while True:
                if observer_active is not None and not observer_active(request):
                    return
                family = getattr(request.state, "native_session_id", None)
                if family and not native.session_active(family, service.access.current_principal()):
                    return
                for event in current.events:
                    yield "id: " + event.event_id + "\ndata: " + event.model_dump_json() + "\n\n"
                position = current.next_cursor or position
                if (
                    current.status not in {"queued", "running"}
                    and not current.has_more
                    and not service.running(request_id)
                ):
                    return
                if not current.has_more:
                    await asyncio.sleep(0.05)
                current = page(request_id, position, 64)

        return StreamingResponse(
            observe(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
