"""Application-loop owned SDK clients and canonical per-tool proxy registrations."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from orion.contracts import ToolCall, ToolDefinition, ToolResult
from orion.integrations.mcp.config import (
    HTTPConfig,
    MCPConfig,
    MCPConfigurationError,
    ServerConfig,
    StdioConfig,
    resolve_environment,
)
from orion.integrations.mcp.schema import adapt_schema, validate_output_schema
from orion.security import redact_public
from orion.tool_runtime.registry import ToolRegistration

MAX_RESULT_BYTES = 64 * 1024
MAX_DISCOVERED_TOOLS = 256
ClientFactory = Callable[[ServerConfig, AsyncExitStack, dict[str, str]], Any]


class _NoWireLogs(logging.Filter):
    """SDK wire/error logs can include raw credentials, payloads and exception bodies."""

    def filter(self, record: logging.LogRecord) -> bool:
        return False


@dataclass
class _Connection:
    config: ServerConfig
    values: dict[str, str] = field(repr=False)
    client: Any = field(default=None, repr=False)
    state: str = "connecting"
    discovered: tuple[str, ...] = ()
    exposed: tuple[str, ...] = ()
    last_error: str | None = None


class MCPManager:
    """One startup snapshot; no reconnect, prompt plane or mutation retry.

    A single owner task enters and exits SDK context managers on the application
    event loop. This preserves AnyIO task/cancel-scope ownership across startup,
    request tasks and shutdown, without an auxiliary loop or asyncio.run().
    """

    def __init__(self, config: MCPConfig, client_factory: ClientFactory | None = None) -> None:
        self._config = config
        self._factory = client_factory or self._sdk_client
        self._connections: dict[str, _Connection] = {}
        self._secrets: tuple[str, ...] = ()
        self._owner: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._registrations: tuple[ToolRegistration, ...] = ()
        # Resolve all required variables before launching any subprocess/HTTP client.
        for server in config.servers:
            values = resolve_environment(
                server.env_from if isinstance(server, StdioConfig) else server.headers_from,
                headers=isinstance(server, HTTPConfig),
            )
            self._connections[server.server_id] = _Connection(server, values)
        secrets = [v for c in self._connections.values() for v in c.values.values()]
        for connection in self._connections.values():
            if isinstance(connection.config, HTTPConfig):
                for header, value in connection.values.items():
                    if header.lower() == "authorization" and " " in value:
                        # Servers may echo the credential without its HTTP auth scheme.
                        credential = value.split(" ", 1)[1].strip()
                        if credential:
                            secrets.append(credential)
        self._secrets = tuple(sorted(set(secrets), key=len, reverse=True))
        for server in config.servers:
            public = server.model_dump_json()
            if any(secret in public for secret in self._secrets):
                raise MCPConfigurationError("secret_in_configuration")

    def _safe(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, "[REDACTED]")
            return redact_public(value)
        if isinstance(value, dict):
            return {self._safe(k): self._safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._safe(item) for item in value]
        return value

    @staticmethod
    async def _sdk_client(
        server: ServerConfig, stack: AsyncExitStack, values: dict[str, str]
    ) -> Client:
        if isinstance(server, StdioConfig):
            # No stderr payload is retained: it may contain credentials or arbitrary text.
            errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
            transport = stdio_client(
                StdioServerParameters(
                    command=server.command, args=server.args, env=values, cwd=server.cwd
                ),
                errlog=errlog,
            )
        else:
            assert isinstance(server, HTTPConfig)
            http = await stack.enter_async_context(
                httpx2.AsyncClient(
                    headers=values,
                    timeout=httpx2.Timeout(
                        min(server.timeout_seconds, 5), read=server.timeout_seconds
                    ),
                    follow_redirects=False,
                    trust_env=False,
                )
            )
            transport = streamable_http_client(server.url, http_client=http)
        return Client(
            transport,
            read_timeout_seconds=server.timeout_seconds,
            cache=None,
            input_required_max_rounds=0,
        )

    async def start(self) -> tuple[ToolRegistration, ...]:
        if self._owner is not None:
            raise MCPConfigurationError("lifecycle")
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._owner = asyncio.create_task(self._serve(ready), name="orion-mcp-clients")
        try:
            await asyncio.wait_for(
                asyncio.shield(ready),
                max(1.0, sum(s.timeout_seconds for s in self._config.servers)),
            )
        except BaseException as error:
            self._owner.cancel()
            await asyncio.gather(self._owner, return_exceptions=True)
            # Consume a concurrently delivered startup exception.
            if ready.done() and not ready.cancelled():
                ready.exception()
            else:
                ready.cancel()
            if isinstance(error, asyncio.CancelledError):
                raise
            category = error.category if isinstance(error, MCPConfigurationError) else "connection"
            raise MCPConfigurationError(category) from None
        return self._registrations

    async def _serve(self, ready: asyncio.Future[None]) -> None:
        wire_filter = _NoWireLogs()
        loggers = [
            logging.getLogger(name)
            for name in tuple(logging.Logger.manager.loggerDict)
            if name == "client" or name.startswith(("mcp.", "httpx2", "httpcore2"))
        ]
        for logger in loggers:
            logger.addFilter(wire_filter)
        try:
            async with AsyncExitStack() as stack:
                registrations: list[ToolRegistration] = []
                for connection in self._connections.values():
                    connection.client = await stack.enter_async_context(
                        await self._factory(connection.config, stack, connection.values)
                    )
                    registrations.extend(await self._discover(connection))
                    connection.state = "connected"
                self._registrations = tuple(registrations)
                ready.set_result(None)
                await self._stop.wait()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            category = error.category if isinstance(error, MCPConfigurationError) else "connection"
            for connection in self._connections.values():
                if connection.state in {"connecting", "connected"}:
                    connection.state, connection.last_error = "failed", category
            if not ready.done():
                ready.set_exception(MCPConfigurationError(category))
        finally:
            for connection in self._connections.values():
                connection.client = None
                if connection.state == "connected":
                    connection.state = "closed"
            for logger in loggers:
                logger.removeFilter(wire_filter)

    async def _discover(self, connection: _Connection) -> list[ToolRegistration]:
        tools: dict[str, Any] = {}
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            page = await connection.client.list_tools(cursor=cursor)
            for tool in page.tools:
                if (
                    not isinstance(tool.name, str)
                    or not 1 <= len(tool.name) <= 128
                    or tool.name in tools
                    or len(tools) >= MAX_DISCOVERED_TOOLS
                ):
                    raise MCPConfigurationError("discovery")
                tools[tool.name] = tool
            cursor = page.next_cursor
            if cursor is None:
                break
            if cursor in seen_cursors or len(seen_cursors) >= 16:
                raise MCPConfigurationError("discovery")
            seen_cursors.add(cursor)
        connection.discovered = tuple(sorted(self._safe(name)[:128] for name in tools))
        registrations: list[ToolRegistration] = []
        for remote, policy in connection.config.tools.items():
            tool = tools.get(remote)
            if tool is None:
                raise MCPConfigurationError("missing_tool")
            description = self._safe(
                tool.description or "External MCP tool (untrusted capability metadata)."
            )
            if not isinstance(description, str) or not 1 <= len(description) <= 2048:
                raise MCPConfigurationError("description")
            # Validate before redaction, so sanitizing cannot hide an unsupported schema.
            schema = adapt_schema(tool.input_schema)
            if self._safe(schema) != schema:
                raise MCPConfigurationError("secret_in_schema")
            if tool.output_schema is not None:
                # The SDK validates structured output itself. Reject references or
                # unbounded/unsupported output contracts before it can resolve them.
                validate_output_schema(tool.output_schema)
                if self._safe(tool.output_schema) != tool.output_schema:
                    raise MCPConfigurationError("secret_in_schema")
            name = f"mcp.{connection.config.server_id}.{policy.alias or remote}"
            definition = ToolDefinition(
                name=name,
                description=description,
                input_schema=self._safe(schema),
                handler_key=name,
                operation_kind=policy.operation_kind,
            )

            async def proxy(
                call: ToolCall,
                remote_name: str = remote,
                conn: _Connection = connection,
                mutation: bool = policy.operation_kind == "mutation",
            ) -> ToolResult:
                return await self._call(conn, remote_name, mutation, call)

            registrations.append(ToolRegistration(definition, proxy))
        connection.exposed = tuple(r.definition.name for r in registrations)
        return registrations

    async def _call(
        self, connection: _Connection, remote: str, mutation: bool, call: ToolCall
    ) -> ToolResult:
        if call.cancellation_requested and call.cancellation_requested():
            raise asyncio.CancelledError
        if connection.client is None or connection.state != "connected":
            return ToolResult.failure(
                call.call_id, call.tool_name, "unavailable", "MCP connection unavailable."
            )
        try:
            async with asyncio.timeout(connection.config.timeout_seconds):
                # Low-level SDK method sends exactly once; no input-required resolver,
                # scope metadata, roots, sampling, elicitation or automatic call retry.
                result = await connection.client.session.call_tool(remote, dict(call.arguments))
        except asyncio.CancelledError:
            raise
        except Exception:
            connection.state, connection.last_error = "failed", "call_transport"
            return ToolResult.failure(
                call.call_id,
                call.tool_name,
                "outcome_unknown" if mutation else "upstream_error",
                "MCP mutation outcome is unknown; do not repeat the mutation."
                if mutation
                else "MCP read failed or timed out.",
            )
        try:
            if not isinstance(result, CallToolResult):
                raise ValueError("invalid result")
            if result.is_error:
                return ToolResult.failure(
                    call.call_id, call.tool_name, "upstream_error", "MCP tool reported failure."
                )
            if len(result.content) > 128 or any(
                not isinstance(c, TextContent) for c in result.content
            ):
                raise ValueError("unsupported content")
            data = {
                "text": [c.text for c in result.content if isinstance(c, TextContent)],
                "structured": result.structured_content,
            }
            if len(json.dumps(data, allow_nan=False).encode()) > MAX_RESULT_BYTES:
                raise ValueError("oversized result")
            data = self._safe(data)
            if len(json.dumps(data, allow_nan=False).encode()) > MAX_RESULT_BYTES:
                raise ValueError("oversized sanitized result")
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status="success",
                data=data,
                sources=(),
            )
        except (ValueError, TypeError, RecursionError):
            connection.last_error = "result"
            return ToolResult.failure(
                call.call_id,
                call.tool_name,
                "outcome_unknown" if mutation else "invalid_result",
                "MCP mutation returned an unverifiable result; do not repeat the mutation."
                if mutation
                else "MCP result is malformed, unsupported or too large.",
            )

    def status(self) -> list[dict[str, object]]:
        return [
            {
                "server_id": c.config.server_id,
                "transport": c.config.transport,
                "state": c.state,
                "discovered_tools": list(c.discovered),
                "exposed_tools": list(c.exposed),
                "last_error": c.last_error,
            }
            for c in self._connections.values()
        ]

    async def close(self) -> None:
        if self._owner is None:
            return
        self._stop.set()
        if self._owner.done():
            await asyncio.gather(self._owner, return_exceptions=True)
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(self._owner), max(10, len(self._connections) * 10)
            )
        except TimeoutError:
            self._owner.cancel()
            await asyncio.gather(self._owner, return_exceptions=True)
