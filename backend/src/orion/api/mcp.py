"""Owner-only MCP transport lifecycle; schemas remain the startup registry snapshot."""

from fastapi import FastAPI, HTTPException

from orion.integrations.mcp import MCPConfigurationError, MCPManager
from orion.integrations.mcp.manager import SUPPORTED_REVISIONS

MCP_OWNER_ROUTES = {
    ("GET", "/api/mcp/servers"),
    ("GET", "/api/mcp/doctor"),
    *(
        ("POST", "/api/mcp/servers/{server_id}/" + action)
        for action in ("connect", "disconnect", "test")
    ),
}


def install_mcp_routes(app: FastAPI, manager: MCPManager | None) -> None:
    @app.get("/api/mcp/servers")
    async def servers() -> list[dict[str, object]]:
        return manager.status() if manager else []

    @app.get("/api/mcp/doctor")
    async def doctor() -> dict[str, object]:
        status = manager.status() if manager else []
        return {
            "healthy": all(item["state"] == "connected" for item in status),
            "supported_revisions": sorted(SUPPORTED_REVISIONS),
            "servers": status,
        }

    async def action(server_id: str, operation: str) -> dict[str, object]:
        if manager is None or server_id not in {item["server_id"] for item in manager.status()}:
            raise HTTPException(404, "MCP server not configured")
        try:
            await getattr(manager, operation)(server_id)
        except MCPConfigurationError as error:
            raise HTTPException(409, "MCP operation unavailable: " + error.category) from None
        return next(item for item in manager.status() if item["server_id"] == server_id)

    @app.post("/api/mcp/servers/{server_id}/connect")
    async def connect(server_id: str) -> dict[str, object]:
        return await action(server_id, "connect")

    @app.post("/api/mcp/servers/{server_id}/disconnect")
    async def disconnect(server_id: str) -> dict[str, object]:
        return await action(server_id, "disconnect")

    @app.post("/api/mcp/servers/{server_id}/test")
    async def test(server_id: str) -> dict[str, object]:
        return await action(server_id, "test")
