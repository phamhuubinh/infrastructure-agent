from __future__ import annotations

import json
from pathlib import Path


SECRETS_PATH = Path("config/secrets.local.json")


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
