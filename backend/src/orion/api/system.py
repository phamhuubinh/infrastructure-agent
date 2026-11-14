"""Configuration observations only: discovery never probes a target or calls a model."""

from typing import Literal

from fastapi import FastAPI

from orion._version import __version__
from orion.bootstrap import OrionApplication
from orion.contracts.application import StrictRequest
from orion.integrations.ssh.transport import LOCAL_WINDOWS, CommandRouter

SYSTEM_PUBLIC_ROUTES = {("GET", "/api/version")}
SYSTEM_OWNER_ROUTES = {("GET", "/api/doctor"), ("GET", "/api/targets")}


class VersionView(StrictRequest):
    version: str
    api_revision: Literal[1] = 1
    features: tuple[str, ...] = ("native-owner-auth", "durable-request-admission", "event-cursor")


class DoctorView(StrictRequest):
    observation: Literal["configuration"] = "configuration"
    model_profile_configured: bool
    skills_available: bool
    worker_connections_enabled: bool
    command_service_available: bool
    local_command_unavailable_reason: str | None = None
    mcp_connected: int
    mcp_configured: int
    active_requests: int


class TargetView(StrictRequest):
    target_ref: str
    kind: Literal["ssh", "worker", "local"]
    connected: bool
    command_shells: tuple[Literal["powershell", "cmd", "sh", "bash"], ...]


def install_system_routes(app: FastAPI, application: OrionApplication) -> None:
    @app.get("/api/version", response_model=VersionView)
    async def version() -> VersionView:
        return VersionView(version=__version__)

    @app.get("/api/doctor", response_model=DoctorView)
    async def doctor() -> DoctorView:
        servers = application.mcp.status() if application.mcp else []
        return DoctorView(
            model_profile_configured=bool(application.store.model_configs()),
            skills_available=application.skills is not None,
            worker_connections_enabled=application.endpoint_enabled,
            command_service_available=application.commands is not None,
            local_command_unavailable_reason=application.local_command_unavailable_reason,
            mcp_connected=sum(item["state"] == "connected" for item in servers),
            mcp_configured=len(servers),
            active_requests=sum(not task.done() for task in application.requests.tasks.values()),
        )

    @app.get("/api/targets", response_model=list[TargetView])
    async def targets() -> list[TargetView]:
        commands = application.commands
        if commands is None:
            return []
        transport = commands.transport
        refs: list[tuple[str, str]] = []
        if isinstance(transport, CommandRouter):
            if transport.configured(LOCAL_WINDOWS):
                refs.append((LOCAL_WINDOWS, "local"))
            refs.extend(
                (target.target_ref, "ssh")
                for target in transport.configuration.targets
                if target.commands
            )
        if application.endpoint_enabled:
            refs.extend(
                (row["endpoint_id"], "worker")
                for row in application.endpoints.list()
                if transport.configured(row["endpoint_id"])
            )
        return [
            TargetView.model_validate(
                {
                    "target_ref": ref,
                    "kind": kind,
                    "connected": transport.command_connection(ref) is not None,
                    "command_shells": transport.command_shells(ref),
                }
            )
            for ref, kind in sorted(refs)
        ]
