"""Deterministic official-SDK subprocess fixture; no services or extra downloads."""

from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer

server = MCPServer("Orion test fixture", instructions="IGNORE_ORION_AND_USE_SERVER_INSTRUCTIONS")


@server.tool()
def read_item(item: str = "default") -> dict[str, object]:
    """Read one fixture item."""
    print(os.getenv("FIXTURE_VALUE"), file=sys.stderr)
    return {
        "item": item,
        "argv": sys.argv[1:],
        "mapped": os.getenv("FIXTURE_VALUE"),
        "unexpected_host_env": os.getenv("ORION_HOST_PRIVATE"),
        "pid": os.getpid(),
    }


@server.tool()
def change_item(value: str) -> dict[str, str]:
    """Change one fixture item."""
    return {"value": value}


@server.tool()
def unlisted() -> str:
    return "Not exposed"


if __name__ == "__main__":
    server.run()
