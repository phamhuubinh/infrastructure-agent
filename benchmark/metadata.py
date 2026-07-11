from __future__ import annotations

import subprocess
import time
from typing import Any


def _get_git_commit() -> str:
    """Get the current git commit hash, or 'unknown' if not available."""
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
    resolved_model: str | None = model

    # Try to resolve model name from servers.json if not provided.
    if resolved_model is None and server_name is not None:
        try:
            import json
            from pathlib import Path
            config_path = Path("servers.json")
            if config_path.exists():
                data = json.loads(config_path.read_text())
                servers: dict[str, object] = data.get("servers", {})
                cfg = servers.get(server_name, {})
                if isinstance(cfg, dict):
                    resolved_model = cfg.get("model")
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timestamp": int(time.time()),
        "git_commit": _get_git_commit(),
        "server": server_name or "",
        "model": resolved_model or "mock",
        "benchmark_version": "1.0",
    }
