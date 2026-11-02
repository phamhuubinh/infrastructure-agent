"""Owner observation and cancellation reuse the scope-owned command service."""

import json
from collections.abc import Callable
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response

from orion.application.commands import CommandService
from orion.contracts import RuntimeScope
from orion.contracts.commands import CommandPage

COMMAND_OWNER_ROUTES = {
    ("GET", "/api/sessions/{session_id}/commands"),
    ("GET", "/api/sessions/{session_id}/commands/{command_id}"),
    ("POST", "/api/sessions/{session_id}/commands/{command_id}/cancel"),
}


def install_command_routes(
    app: FastAPI,
    service: CommandService | None,
    scope_for_session: Callable[[str], RuntimeScope],
) -> None:
    def available() -> CommandService:
        if service is None:
            raise HTTPException(503, "Command service unavailable")
        return service

    def record(scope: RuntimeScope, identity: str) -> dict[str, object]:
        current = available()
        with current.store._lock:
            row = current.store._connection.execute(
                "SELECT command_id,target_ref FROM command_records WHERE command_id=? "
                "AND session_id=? AND principal_id=? AND workspace_id=? "
                "AND project_id IS ? AND endpoint_id IS ?",
                (
                    identity,
                    scope.session_id,
                    scope.principal_id,
                    scope.workspace_id,
                    scope.project_id,
                    scope.endpoint_id,
                ),
            ).fetchone()
        if row is None:
            raise HTTPException(404, "Command not found")
        return dict(row)

    @app.get("/api/sessions/{session_id}/commands", response_model=list[CommandPage])
    async def list_commands(
        session_id: str,
        response: Response,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=64)] = 32,
    ) -> list[CommandPage]:
        scope = scope_for_session(session_id)
        current = available()
        response.headers["Cache-Control"] = "no-store"
        with current.store._lock:
            rows = current.store._connection.execute(
                "SELECT observation_json FROM command_records WHERE session_id=? "
                "AND principal_id=? AND workspace_id=? AND project_id IS ? AND endpoint_id IS ? "
                "ORDER BY created_at,command_id LIMIT ? OFFSET ?",
                (
                    scope.session_id,
                    scope.principal_id,
                    scope.workspace_id,
                    scope.project_id,
                    scope.endpoint_id,
                    limit,
                    offset,
                ),
            ).fetchall()
        return [CommandPage.model_validate(json.loads(row["observation_json"])) for row in rows]

    @app.get("/api/sessions/{session_id}/commands/{command_id}", response_model=CommandPage)
    async def status(
        session_id: str,
        command_id: str,
        response: Response,
        stdout_offset: Annotated[int, Query(ge=0, le=4_194_304)] = 0,
        stderr_offset: Annotated[int, Query(ge=0, le=4_194_304)] = 0,
    ) -> CommandPage:
        scope = scope_for_session(session_id)
        target = str(record(scope, command_id)["target_ref"])
        response.headers["Cache-Control"] = "no-store"
        try:
            return await available().status(scope, target, command_id, stdout_offset, stderr_offset)
        except (PermissionError, ValueError):
            raise HTTPException(409, "Command observation unavailable") from None

    @app.post("/api/sessions/{session_id}/commands/{command_id}/cancel", response_model=CommandPage)
    async def cancel(session_id: str, command_id: str, response: Response) -> CommandPage:
        scope = scope_for_session(session_id)
        target = str(record(scope, command_id)["target_ref"])
        response.headers["Cache-Control"] = "no-store"
        try:
            return await available().cancel(scope, target, command_id)
        except (PermissionError, ValueError):
            raise HTTPException(409, "Command cancellation unavailable") from None
