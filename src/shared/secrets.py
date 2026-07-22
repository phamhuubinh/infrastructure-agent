from __future__ import annotations

import json
import os
from pathlib import Path


def _default_project_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent.parent / "config" / "secrets.local.json"
    )


def _resolve_secrets_path() -> Path:
    """Resolve secrets path from ORION_SECRETS_PATH env var or default."""
    env_path = os.environ.get("ORION_SECRETS_PATH")
    if env_path:
        return Path(env_path)
    return _default_project_path()


SECRETS_PATH = _resolve_secrets_path()


def get_tool_config(tool_name: str) -> dict[str, str] | None:
    """Get configuration for a specific tool from config/secrets.local.json.

    Args:
        tool_name: The tool name (e.g. "grafana", "zabbix").

    Returns:
        A dict with config keys (url, token, etc.) or None if not found.
    """
    try:
        secrets = load_secrets()
        return secrets.get(tool_name)
    except (FileNotFoundError, ValueError):
        return None


def load_secrets() -> dict[str, dict[str, str]]:
    """Load secrets from config/secrets.local.json.

    Returns a dict keyed by tool name (e.g. "grafana", "zabbix")
    with nested "url" and "token" fields.

    Raises:
        FileNotFoundError: if config/secrets.local.json does not exist.
        ValueError: if the file contains invalid JSON.
    """
    if not SECRETS_PATH.exists():
        msg = f"Secrets file not found at {SECRETS_PATH}"
        raise FileNotFoundError(msg)

    try:
        raw = SECRETS_PATH.read_text()
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"{SECRETS_PATH} contains invalid JSON: {exc}"
        raise ValueError(msg) from exc

    if not isinstance(data, dict):
        msg = f"{SECRETS_PATH} must be a JSON object at the top level"
        raise ValueError(msg)

    return data
