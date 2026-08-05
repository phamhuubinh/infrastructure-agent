from __future__ import annotations

import json
import logging
from pathlib import Path

from src.tool.execution_backend import (
    ExecutionBackend,
    LocalExecutionBackend,
    SSHExecutionBackend,
)

DEFAULT_TARGETS: dict[str, ExecutionBackend] = {
    "localhost": LocalExecutionBackend(),
}

DEFAULT_TARGET_METADATA: dict[str, dict[str, str]] = {
    "localhost": {
        "display_name": "orion-api",
        "execution_scope": "orion-runtime",
        "description": (
            "The Orion process environment; in Docker this is the API container, "
            "not the physical Docker host."
        ),
    }
}


class TargetStore:
    def __init__(self, path: str = "targets.json") -> None:
        self._path = Path(path)

    def load(self) -> dict[str, ExecutionBackend]:
        if not self._path.exists():
            return dict(DEFAULT_TARGETS)

        raw = self._path.read_text()
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError:
            logging.getLogger(__name__).error(
                "Failed to decode JSON from %s, returning default targets", self._path
            )
            return dict(DEFAULT_TARGETS)
        if not isinstance(parsed, dict):
            return dict(DEFAULT_TARGETS)
        entries = parsed.get("targets", parsed)
        if not isinstance(entries, dict):
            return dict(DEFAULT_TARGETS)
        targets: dict[str, ExecutionBackend] = {}
        for raw_name, cfg in entries.items():
            name = str(raw_name)
            backend_type = (
                cfg.get("backend", "local") if isinstance(cfg, dict) else "local"
            )
            if not isinstance(cfg, dict):
                targets[name] = LocalExecutionBackend()
            elif backend_type == "ssh":
                port_value = cfg.get("port", 22)
                port = int(port_value) if isinstance(port_value, (str, int)) else 22
                identity_value = cfg.get("identity_file")
                identity_file = (
                    identity_value if isinstance(identity_value, str) else None
                )
                targets[name] = SSHExecutionBackend(
                    host=str(cfg.get("host", "")),
                    user=str(cfg.get("user", "root")),
                    port=port,
                    identity_file=identity_file,
                    strict_host_key_checking=bool(
                        cfg.get("strict_host_key_checking", False)
                    ),
                )
            else:
                targets[name] = LocalExecutionBackend()
        return targets

    def load_metadata(self) -> dict[str, dict[str, str]]:
        """Load non-secret target identity fields independently of backends."""

        if not self._path.exists():
            return {name: dict(value) for name, value in DEFAULT_TARGET_METADATA.items()}
        try:
            parsed = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError):
            return {name: dict(value) for name, value in DEFAULT_TARGET_METADATA.items()}
        if not isinstance(parsed, dict):
            return {}
        entries = parsed.get("targets", parsed)
        if not isinstance(entries, dict):
            return {}
        metadata: dict[str, dict[str, str]] = {}
        for raw_name, raw_cfg in entries.items():
            if not isinstance(raw_cfg, dict):
                continue
            name = str(raw_name)
            defaults = DEFAULT_TARGET_METADATA.get(name, {})
            metadata[name] = {
                "display_name": str(raw_cfg.get("display_name", defaults.get("display_name", name))),
                "execution_scope": str(
                    raw_cfg.get("execution_scope", defaults.get("execution_scope", "remote-host"))
                ),
                "description": str(raw_cfg.get("description", defaults.get("description", ""))),
            }
        return metadata

    def save(self, backends: dict[str, ExecutionBackend]) -> None:
        existing_metadata = self.load_metadata() if self._path.exists() else {}
        data: dict[str, dict[str, object]] = {}
        for name, backend in backends.items():
            if isinstance(backend, SSHExecutionBackend):
                data[name] = {
                    "backend": "ssh",
                    "host": backend._host,
                    "port": backend._port,
                    "user": backend._user,
                    "identity_file": backend._identity_file,
                    "strict_host_key_checking": backend._strict_host_key_checking,
                }
            else:
                data[name] = {"backend": "local"}
            metadata = existing_metadata.get(name, {})
            for key in ("display_name", "execution_scope", "description"):
                if metadata.get(key):
                    data[name][key] = metadata[key]
        self._path.write_text(json.dumps({"targets": data}, indent=2))
