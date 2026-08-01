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

    def save(self, backends: dict[str, ExecutionBackend]) -> None:
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
        self._path.write_text(json.dumps({"targets": data}, indent=2))
