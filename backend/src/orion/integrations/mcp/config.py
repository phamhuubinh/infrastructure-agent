"""Strict local administrative MCP configuration; never model-selected authority."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")]
EnvName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")]
RemoteName = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
MAX_CONFIG_BYTES = 128 * 1024


class MCPConfigurationError(ValueError):
    """Safe category-only administrative error, without raw config or SDK exceptions."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"MCP startup failed: {category}.")


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ToolPolicy(StrictConfig):
    operation_kind: Literal["read", "mutation"]
    alias: Identifier | None = None


class ServerConfig(StrictConfig):
    transport: Literal["stdio", "streamable_http"]
    server_id: Identifier
    tools: dict[RemoteName, ToolPolicy] = Field(min_length=1, max_length=128)
    timeout_seconds: float = Field(default=30.0, ge=0.1, le=120)

    @model_validator(mode="after")
    def aliases(self) -> ServerConfig:
        aliases: set[str] = set()
        for name, policy in self.tools.items():
            alias = policy.alias or name
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,19}", alias) or alias in aliases:
                raise ValueError("invalid or duplicate alias")
            aliases.add(alias)
        return self


class StdioConfig(ServerConfig):
    transport: Literal["stdio"]
    command: str = Field(min_length=1, max_length=4096)
    args: list[Annotated[str, Field(max_length=4096)]] = Field(default_factory=list, max_length=64)
    env_from: dict[EnvName, EnvName] = Field(default_factory=dict, max_length=64)
    cwd: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def process_fields(self) -> StdioConfig:
        if any("\x00" in part for part in [self.command, *self.args]):
            raise ValueError("invalid argv")
        if any(
            re.search(r"(?i)(token|password|secret|api[-_]?key|authorization)", a)
            for a in self.args
        ):
            raise ValueError("secrets must use environment")
        if self.cwd is not None and (
            not Path(self.cwd).is_absolute() or not Path(self.cwd).is_dir()
        ):
            raise ValueError("invalid cwd")
        return self


class HTTPConfig(ServerConfig):
    transport: Literal["streamable_http"]
    url: str = Field(min_length=1, max_length=2048)
    headers_from: dict[str, EnvName] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def endpoint_and_headers(self) -> HTTPConfig:
        url = urlsplit(self.url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(c.isspace() or ord(c) < 32 for c in self.url)
        ):
            raise ValueError("invalid endpoint")
        _ = url.port
        seen: set[str] = set()
        for header in self.headers_from:
            lower = header.lower()
            if (
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", header)
                or (lower != "authorization" and not lower.startswith("x-"))
                or lower.startswith(("x-forwarded-", "x-mcp-"))
                or lower in seen
            ):
                raise ValueError("unsafe header")
            seen.add(lower)
        return self


class MCPConfig(StrictConfig):
    servers: list[Annotated[StdioConfig | HTTPConfig, Field(discriminator="transport")]] = Field(
        default_factory=list, max_length=16
    )

    @model_validator(mode="after")
    def server_ids(self) -> MCPConfig:
        ids = [server.server_id for server in self.servers]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate server ID")
        return self


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_config() -> MCPConfig:
    path = os.getenv("ORION_MCP_CONFIG")
    if not path:
        return MCPConfig()
    try:
        with Path(path).open("rb") as stream:
            payload = stream.read(MAX_CONFIG_BYTES + 1)
        if len(payload) > MAX_CONFIG_BYTES:
            raise ValueError("oversized config")
        return MCPConfig.model_validate(json.loads(payload, object_pairs_hook=_unique_object))
    except (OSError, ValueError, ValidationError, RecursionError):
        raise MCPConfigurationError("configuration") from None


def resolve_environment(mapping: dict[str, str], *, headers: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    for target, source in mapping.items():
        value = os.getenv(source)
        if not value:
            raise MCPConfigurationError("missing_environment")
        if "\x00" in value or len(value) > 8192 or (headers and any(c in value for c in "\r\n")):
            raise MCPConfigurationError("invalid_environment")
        result[target] = value
    return result
