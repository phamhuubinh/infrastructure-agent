from __future__ import annotations

import json
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
        data: dict[str, object] = json.loads(raw)
        entries: dict[str, dict[str, object]] = data.get("targets", data)
        targets: dict[str, ExecutionBackend] = {}
        for name, cfg in entries.items():
            backend_type = (
                cfg.get("backend", "local") if isinstance(cfg, dict) else "local"
            )
            if not isinstance(cfg, dict):
                targets[name] = LocalExecutionBackend()
            elif backend_type == "ssh":
                targets[name] = SSHExecutionBackend(
                    host=str(cfg.get("host", "")),
                    user=str(cfg.get("user", "root")),
                    port=int(cfg.get("port", 22)),
                    identity_file=cfg.get("identity_file"),
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
                }
            else:
                data[name] = {"backend": "local"}
        self._path.write_text(json.dumps({"targets": data}, indent=2))
