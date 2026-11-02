"""Offline MCP configuration listing and bounded tools-only discovery diagnostics."""

import argparse
import asyncio
import json

from orion.integrations.mcp import MCPConfig, MCPConfigurationError, MCPManager, load_config


async def diagnose(config: MCPConfig) -> list[dict[str, object]]:
    manager = MCPManager(config)
    try:
        await manager.start()
        for item in manager.status():
            await manager.test(str(item["server_id"]))
        return manager.status()
    finally:
        await manager.close()


def run_mcp_command(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="orion mcp")
    parser.add_argument("operation", choices=("list", "doctor", "test"))
    parser.add_argument("server_id", nargs="?")
    options = parser.parse_args(arguments)
    try:
        config = load_config()
        if options.server_id:
            selected = [
                server for server in config.servers if server.server_id == options.server_id
            ]
            if not selected:
                raise MCPConfigurationError("not_configured")
            config = MCPConfig(servers=selected)
        if options.operation == "list":
            result: dict[str, object] = {
                "servers": [
                    {
                        "server_id": server.server_id,
                        "transport": server.transport,
                        "tools": sorted(
                            policy.alias or name for name, policy in server.tools.items()
                        ),
                    }
                    for server in config.servers
                ]
            }
        else:
            result = {
                "healthy": True,
                "servers": asyncio.run(diagnose(config)),
                "scope": "temporary diagnostic connections closed on completion; no tool invoked",
            }
    except (MCPConfigurationError, OSError, RuntimeError):
        raise SystemExit(
            "MCP operation failed. Check the configured server and credential references."
        ) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    print(json.dumps(result, ensure_ascii=True))
