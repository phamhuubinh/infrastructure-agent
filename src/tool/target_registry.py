from __future__ import annotations

from src.tool.execution_backend import (
    ExecutionBackend,
    LocalExecutionBackend,
)
from src.tool.linux_tool import LinuxTool
from src.tool.target_store import TargetStore
from src.tool.tool import Tool


class TargetRegistry:
    """Registry for investigation targets and domain tools.

    Maintains two separate namespaces:
    - Targets: infrastructure machines accessible via ExecutionBackend
      (SSH, local). Each target gets a LinuxTool automatically.
    - Domain tools: external services (Zabbix, Grafana) that provide
      operational data via API. These are registered explicitly.

    The separation ensures that a target named "monitor" (a Linux machine)
    does not collide with a domain tool registered as "zabbix" (an API).
    """

    def __init__(
        self,
        store: TargetStore | None = None,
    ) -> None:
        self._store = store
        self._backends: dict[str, ExecutionBackend] = {}
        self._domain_tools: dict[str, Tool] = {}

        if store is not None:
            self._backends = store.load()

    def add(
        self,
        name: str,
        backend: ExecutionBackend | None = None,
    ) -> None:
        """Register a target machine accessible via ExecutionBackend.

        A LinuxTool is automatically created for this target.
        """
        if name in self._backends:
            raise ValueError(f"Target '{name}' is already registered.")

        backend = backend or LocalExecutionBackend()
        self._backends[name] = backend

        if self._store is not None:
            self._store.save(self._backends)

    def remove(
        self,
        name: str,
    ) -> None:
        if name not in self._backends:
            raise KeyError(f"Unknown target: '{name}'.")

        del self._backends[name]

        if self._store is not None:
            self._store.save(self._backends)

    def register_domain_tool(
        self,
        name: str,
        tool: Tool,
    ) -> None:
        """Register a domain tool (Zabbix, Grafana, ...) by name.

        Domain tool names must be unique across both domain tools
        and target backends to prevent ambiguity in KnowledgeTool dispatch.
        """
        if name in self._domain_tools:
            raise ValueError(f"Domain tool '{name}' is already registered.")
        if name in self._backends:
            raise ValueError(
                f"Domain tool '{name}' conflicts with an existing "
                f"target backend. Choose a different name."
            )
        self._domain_tools[name] = tool

    register_tool = register_domain_tool  # backward compatibility alias

    def get_tool(self, name: str) -> Tool:
        """Get the Tool for a given name — could be a target or domain tool.

        Domain tools take precedence over targets.
        If no domain tool is registered for this name, returns a LinuxTool
        for the target backend.
        """
        # Check domain tools first.
        domain_tool = self._domain_tools.get(name)
        if domain_tool is not None:
            return domain_tool

        # Fall back to target backend → LinuxTool.
        backend = self._backends.get(name)
        if backend is not None:
            return LinuxTool(backend=backend)

        raise KeyError(f"Unknown target or domain tool: '{name}'.")

    def target_names(self) -> list[str]:
        return sorted(set(self._backends) | set(self._domain_tools))

    def backend(self, name: str) -> ExecutionBackend | None:
        return self._backends.get(name)
