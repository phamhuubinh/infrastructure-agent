from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Server config (servers.json)
# ---------------------------------------------------------------------------


class ServerConfig(BaseModel):
    """Configuration for a single model server."""

    base_url: str
    api_key: str | None = None
    model: str = "gpt-4"
    provider: str | None = None
    timeout: int = Field(default=60, ge=1, le=300)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)


class ServersConfig(BaseModel):
    """Top-level servers.json schema."""

    active_server: str = ""
    servers: dict[str, ServerConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def active_must_exist(self) -> ServersConfig:
        if not self.servers:
            if self.active_server:
                raise ValueError(
                    "active_server must be empty when no model is configured"
                )
            return self
        if self.active_server not in self.servers:
            available = ", ".join(sorted(self.servers))
            raise ValueError(
                f"active_server '{self.active_server}' is not defined "
                f"in servers. Available servers: {available}"
            )
        return self


# ---------------------------------------------------------------------------
# Tool config (tools.json)
# ---------------------------------------------------------------------------


class ToolEntry(BaseModel):
    """A single tool entry in tools.json."""

    model_config = {"extra": "allow"}

    tool: str
    url: str | None = None
    token: str | None = None
    target: str | None = None
    timeout: int | None = None


def _validate_tools_dict(data: dict[str, Any]) -> dict[str, ToolEntry]:
    """Validate each entry in tools.json against ToolEntry."""
    result: dict[str, ToolEntry] = {}
    for name, entry in data.items():
        if isinstance(entry, dict):
            result[name] = ToolEntry.model_validate(entry)
        else:
            raise ValueError(
                f"tools.json entry '{name}' must be a JSON object, "
                f"got {type(entry).__name__}"
            )
    return result


# ---------------------------------------------------------------------------
# Target config (targets.json)
# ---------------------------------------------------------------------------


class TargetEntry(BaseModel):
    """A single target entry in targets.json."""

    model_config = {"extra": "allow"}

    backend: str
    host: str | None = None
    user: str | None = None


class TargetsConfig(BaseModel):
    """Top-level targets.json schema."""

    default: str | None = None
    targets: dict[str, TargetEntry]


# ---------------------------------------------------------------------------
# Validation entry point
# ---------------------------------------------------------------------------


class ConfigValidationError(Exception):
    """Raised when one or more configuration files fail schema validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        detail = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"Configuration validation failed:\n{detail}")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _servers_path() -> Path:
    configured = os.environ.get("ORION_SERVERS_FILE", "").strip()
    return Path(configured) if configured else _project_root() / "servers.json"


def _load_json(path: Path) -> dict[str, Any]:
    """Load and parse a JSON file, returning the parsed dict."""
    raw = path.read_text()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object at the top level")
    return data


def validate_all_configs() -> None:
    """Validate servers.json, tools.json, and targets.json at startup.

    Raises:
        ConfigValidationError: if any config file fails validation.
    """
    root = _project_root()
    errors: list[str] = []

    # --- servers.json ---
    servers_path = _servers_path()
    if servers_path.exists():
        try:
            data = _load_json(servers_path)
            ServersConfig.model_validate(data)
        except Exception as exc:
            errors.append(f"servers.json: {exc}")

    # --- tools.json ---
    tools_path = root / "tools.json"
    if tools_path.exists():
        try:
            data = _load_json(tools_path)
            _validate_tools_dict(data)
        except Exception as exc:
            errors.append(f"tools.json: {exc}")

    # --- targets.json ---
    targets_path = root / "targets.json"
    if targets_path.exists():
        try:
            data = _load_json(targets_path)
            TargetsConfig.model_validate(data)
        except Exception as exc:
            errors.append(f"targets.json: {exc}")

    if errors:
        raise ConfigValidationError(errors)
