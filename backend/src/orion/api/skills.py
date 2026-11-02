"""Owner skill management accepts package bytes, never a server filesystem path."""

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI, HTTPException, Request

from orion.access import LocalAccessAdapter
from orion.contracts import RuntimeScope
from orion.contracts.application import StrictRequest
from orion.contracts.skills import SkillDescriptor
from orion.skills.archive import MAX_ARCHIVE_BYTES, archive_resources
from orion.skills.packages import SkillPackageError
from orion.skills.service import SkillError, SkillService

SKILL_OWNER_ROUTES = {
    ("GET", "/api/sessions/{session_id}/skills"),
    ("POST", "/api/skills/packages"),
    ("PATCH", "/api/skills/{name}"),
    ("DELETE", "/api/skills/{name}"),
}


class SkillPreference(StrictRequest):
    source: Literal["bundled", "user", "project"]
    project_id: str | None = None
    enabled: bool


def install_skill_routes(
    app: FastAPI,
    service: SkillService | None,
    access: LocalAccessAdapter,
    scope_for_session: Callable[[str], RuntimeScope],
) -> None:
    def available() -> SkillService:
        if service is None:
            raise HTTPException(503, "Skill catalog unavailable")
        return service

    @app.get("/api/sessions/{session_id}/skills", response_model=list[SkillDescriptor])
    async def catalog(session_id: str) -> list[SkillDescriptor]:
        scope = scope_for_session(session_id)
        try:
            return list(available().catalog(scope).values())
        except SkillError:
            raise HTTPException(409, "Skill catalog unavailable") from None

    @app.post(
        "/api/skills/packages",
        response_model=SkillDescriptor,
        status_code=201,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                },
            }
        },
    )
    async def install_package(
        request: Request,
        source: Literal["user", "project"] = "user",
        project_id: str | None = None,
    ) -> SkillDescriptor:
        current = available()
        if request.headers.get("content-type", "").partition(";")[0] != "application/octet-stream":
            raise HTTPException(415, "Expected a ZIP package as application/octet-stream")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_ARCHIVE_BYTES:
                raise HTTPException(413, "Skill package exceeds limit")
            body.extend(chunk)
        principal = access.current_principal()
        try:
            return current.install_resources(
                archive_resources(bytes(body)),
                source,
                principal.principal_id,
                principal.workspace_id,
                project_id,
            )
        except (SkillError, SkillPackageError):
            raise HTTPException(422, "Invalid product skill package or scope") from None

    @app.patch("/api/skills/{name}", status_code=204)
    async def preference(name: str, body: SkillPreference) -> None:
        principal = access.current_principal()
        try:
            available().set_enabled(
                name,
                body.source,
                body.enabled,
                principal.principal_id,
                principal.workspace_id,
                body.project_id,
            )
        except SkillError:
            raise HTTPException(404, "Skill unavailable") from None

    @app.delete("/api/skills/{name}", status_code=204)
    async def remove(
        name: str, source: Literal["user", "project"], project_id: str | None = None
    ) -> None:
        principal = access.current_principal()
        try:
            available().remove(
                name, source, principal.principal_id, principal.workspace_id, project_id
            )
        except SkillError:
            raise HTTPException(404, "Skill unavailable") from None
