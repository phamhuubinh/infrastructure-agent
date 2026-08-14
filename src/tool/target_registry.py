from __future__ import annotations

from dataclasses import dataclass

from src.tool.execution_backend import (
    ExecutionBackend,
    LocalExecutionBackend,
    SSHExecutionBackend,
)
from src.tool.linux import LinuxTool
from src.tool.target_preflight import DEFAULT_TARGET_PREFLIGHT, EnvironmentFingerprint
from src.tool.target_store import TargetStore
from src.tool.tool import Tool


@dataclass(frozen=True, slots=True)
class TargetIdentity:
    name: str
    display_name: str
    execution_scope: str
    backend_type: str
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "execution_scope": self.execution_scope,
            "backend_type": self.backend_type,
            "description": self.description,
        }


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
        self._linux_tools: dict[str, LinuxTool] = {}
        self._metadata: dict[str, dict[str, str]] = {}
        self._preflight = DEFAULT_TARGET_PREFLIGHT

        if store is not None:
            self._backends = store.load()
            self._metadata = store.load_metadata()

    def add(
        self,
        name: str,
        backend: ExecutionBackend | None = None,
        strict_host_key_checking: bool | None = None,
    ) -> None:
        """Register a target machine accessible via ExecutionBackend.

        A LinuxTool is automatically created for this target.
        """
        if name in self._backends:
            msg = f"Target '{name}' is already registered."
            raise ValueError(msg)

        backend = backend or LocalExecutionBackend()
        if strict_host_key_checking is not None:
            if not isinstance(backend, SSHExecutionBackend):
                msg = "Host key checking can only be configured for SSH targets."
                raise ValueError(msg)
            backend._strict_host_key_checking = strict_host_key_checking
        self._backends[name] = backend
        self._metadata.setdefault(
            name,
            {
                "display_name": "orion-api" if name == "localhost" else name,
                "execution_scope": (
                    "orion-runtime"
                    if isinstance(backend, LocalExecutionBackend)
                    else "remote-host"
                ),
                "description": "",
            },
        )

        if self._store is not None:
            self._store.save(self._backends)

    def remove(
        self,
        name: str,
    ) -> None:
        if name not in self._backends:
            msg = f"Unknown target: '{name}'."
            raise KeyError(msg)

        del self._backends[name]
        self._linux_tools.pop(name, None)
        self._metadata.pop(name, None)
        self._preflight.invalidate(name)

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
            msg = f"Domain tool '{name}' is already registered."
            raise ValueError(msg)
        if name in self._backends:
            msg = (
                f"Domain tool '{name}' conflicts with an existing "
                f"target backend. Choose a different name."
            )
            raise ValueError(msg)
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
            tool = self._linux_tools.get(name)
            if tool is None:
                tool = LinuxTool(
                    backend=backend,
                    target_identity=self.identity(name).to_dict(),
                )
                self._linux_tools[name] = tool
            return tool

        msg = f"Unknown target or domain tool: '{name}'."
        raise KeyError(msg)

    def target_names(self) -> list[str]:
        return sorted(set(self._backends) | set(self._domain_tools))

    def domain_tool_names(self) -> tuple[str, ...]:
        """Return configured provider names without exposing registry internals."""

        return tuple(sorted(self._domain_tools))

    def backend(self, name: str) -> ExecutionBackend | None:
        return self._backends.get(name)

    def identity(self, name: str) -> TargetIdentity:
        backend = self._backends.get(name)
        if backend is None:
            raise KeyError(f"Unknown infrastructure target: '{name}'.")
        metadata = self._metadata.get(name, {})
        return TargetIdentity(
            name=name,
            display_name=str(metadata.get("display_name", name)),
            execution_scope=str(
                metadata.get(
                    "execution_scope",
                    "orion-runtime"
                    if isinstance(backend, LocalExecutionBackend)
                    else "remote-host",
                )
            ),
            backend_type=("ssh" if isinstance(backend, SSHExecutionBackend) else "local"),
            description=str(metadata.get("description", "")),
        )

    def preflight(
        self, name: str, *, force: bool = False
    ) -> EnvironmentFingerprint:
        backend = self._backends.get(name)
        if backend is None:
            raise KeyError(f"Unknown infrastructure target: '{name}'.")
        return self._preflight.inspect(name, backend, force=force)
