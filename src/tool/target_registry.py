from __future__ import annotations

from dataclasses import dataclass

from src.tool.execution_backend import (
    ExecutionBackend,
    LocalExecutionBackend,
)
from src.tool.linux_tool import LinuxTool
from src.tool.target_store import TargetStore
from src.tool.tool import Tool


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    backend: ExecutionBackend


class TargetRegistry:
    def __init__(
        self,
        store: TargetStore | None = None,
    ) -> None:
        self._store = store
        self._backends: dict[str, ExecutionBackend] = {}
        self._tools: dict[str, Tool] = {}

        if store is not None:
            self._backends = store.load()
            for name, backend in self._backends.items():
                self._tools[name] = LinuxTool(backend=backend)

    def add(
        self,
        name: str,
        backend: ExecutionBackend | None = None,
    ) -> None:
        if name in self._backends:
            raise ValueError(f"Target '{name}' is already registered.")

        backend = backend or LocalExecutionBackend()
        self._backends[name] = backend
        self._tools[name] = LinuxTool(backend=backend)

        if self._store is not None:
            self._store.save(self._backends)

    def remove(
        self,
        name: str,
    ) -> None:
        if name not in self._backends:
            raise KeyError(f"Unknown target: '{name}'.")

        del self._backends[name]
        del self._tools[name]

        if self._store is not None:
            self._store.save(self._backends)

    def register_tool(
        self,
        name: str,
        tool: Tool,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Target '{name}' is already registered.")
        self._tools[name] = tool

    def get_tool(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown target: '{name}'.") from exc

    def target_names(self) -> list[str]:
        return sorted(self._tools)

    def backends(self) -> dict[str, ExecutionBackend]:
        return dict(self._backends)
