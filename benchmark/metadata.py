from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any


def _get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


def _resolve_server_config(
    server_name: str | None,
) -> dict[str, Any]:
    """Load a server config from servers.json, returning {} on failure."""
    if server_name is None:
        return {}
    try:
        config_path = Path("servers.json")
        if not config_path.exists():
            return {}
        data = json.loads(config_path.read_text())
        servers: dict[str, Any] = data.get("servers", {})
        cfg = servers.get(server_name, {})
        return dict(cfg) if isinstance(cfg, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def collect_benchmark_metadata(
    server_name: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Collect metadata for a benchmark run.

    Args:
        server_name: The server name from servers.json (if any).
        model: The model name override (if any).

    Returns:
        A dict with benchmark metadata fields.
    """
    config = _resolve_server_config(server_name)
    resolved_model: str | None = model or config.get("model")

    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timestamp": int(time.time()),
        "git_commit": _get_git_commit(),
        "server": server_name or "",
        "model": resolved_model or "mock",
        "provider": config.get("provider", ""),
        "benchmark_version": "1.0",
    }
