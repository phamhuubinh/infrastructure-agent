from __future__ import annotations

import json
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


SECRETS_PATH = _project_root() / "config" / "secrets.local.json"


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
        raise FileNotFoundError(
            "Thiếu config/secrets.local.json, xem README để biết cấu trúc file"
        )

    try:
        raw = SECRETS_PATH.read_text()
        data: dict[str, dict[str, str]] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"config/secrets.local.json chứa JSON không hợp lệ: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "config/secrets.local.json phải là một JSON object ở cấp cao nhất"
        )

    return data
