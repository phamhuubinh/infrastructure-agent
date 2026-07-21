from __future__ import annotations

import inspect
import time as _time

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.shared.logger import error, info
from src.tool.execution_backend import ExecutionBackend, LocalExecutionBackend
from src.tool.tool import Tool

from .capabilities.cpu import (
    _get_boot_time,
    _get_cpu,
    _get_cpu_usage,
    _get_system,
    _get_system_load,
    _get_uptime,
)
from .capabilities.disk import (
    _get_block_device,
    _get_disk,
    _get_disk_usage,
    _get_filesystem,
    _get_filesystem_health,
)
from .capabilities.memory import _get_memory, _get_swap
from .capabilities.network import _get_dns, _get_listening_ports, _get_network
from .capabilities.package import _get_package, _search_package
from .capabilities.process import _get_process, _get_process_by_name, _search_process
from .capabilities.security import (
    _get_apparmor,
    _get_certificate,
    _get_firewall,
    _get_secureboot,
    _get_selinux,
    _get_ssh,
)
from .capabilities.service import (
    _get_docker,
    _get_lxd,
    _get_service,
    _get_services,
    _search_service,
)
from .capabilities.system import (
    _get_environment,
    _get_gpu,
    _get_hardware,
    _get_journal,
    _get_locale,
    _get_log,
    _get_module,
    _get_pci,
    _get_recent_logins,
    _get_session,
    _get_time,
    _get_time_sync,
    _get_usb,
    _get_user,
)

_CAPABILITIES: dict[str, Capability] = {
    "get_system": Capability(
        "get_system",
        _get_system,
        "system",
        ("identity", "inventory"),
        ("get_memory", "get_disk"),
        ("system-identity",),
        description="Collect general system identity and hardware inventory",
        supported_targets=("localhost",),
        parameters=("source", "resource"),
        estimated_cost=0.1,
    ),
    "get_network": Capability(
        "get_network",
        _get_network,
        "network",
        ("health", "connectivity"),
        ("get_dns", "get_listening_ports"),
        ("network", "interface", "ip", "gateway", "routing", "network_usage"),
        description="Collect network interfaces, IP addresses, and routing info",
        supported_targets=("localhost",),
        parameters=("source", "resource"),
        estimated_cost=0.2,
    ),
    "get_services": Capability(
        "get_services",
        _get_services,
        "system",
        ("services", "health"),
        ("get_service", "search_service", "get_listening_ports"),
        ("services", "dependencies"),
        description="List all system services and their current status",
        supported_targets=("localhost",),
        parameters=("source", "resource"),
        estimated_cost=0.2,
    ),
    "search_service": Capability(
        "search_service",
        _search_service,
        "system",
        ("services", "discovery"),
        ("get_service", "get_listening_ports"),
        ("services", "application-discovery", "service_discovery"),
    ),
    "get_docker": Capability(
        "get_docker",
        _get_docker,
        "container",
        ("container", "health"),
        ("get_services",),
        ("container",),
    ),
    "get_cpu": Capability(
        "get_cpu",
        _get_cpu,
        "system",
        ("health", "performance"),
        ("get_cpu_usage", "get_memory"),
        ("cpu",),
    ),
    "get_memory": Capability(
        "get_memory",
        _get_memory,
        "system",
        ("health", "performance"),
        ("get_swap", "get_system_load"),
        ("memory", "memory_usage"),
    ),
    "get_disk": Capability(
        "get_disk",
        _get_disk,
        "storage",
        ("storage", "health"),
        ("get_filesystem", "get_block_device", "get_disk_usage"),
        ("storage",),
    ),
    "get_filesystem": Capability(
        "get_filesystem",
        _get_filesystem,
        "storage",
        ("storage", "health"),
        ("get_disk",),
        ("filesystem", "mount", "filesystem_discovery"),
    ),
    "get_dns": Capability(
        "get_dns",
        _get_dns,
        "network",
        ("dns", "connectivity"),
        ("get_network",),
        ("dns",),
    ),
    "get_process": Capability(
        "get_process",
        _get_process,
        "system",
        ("processes", "performance"),
        ("search_process", "get_memory", "get_cpu_usage"),
        ("processes",),
    ),
    "search_process": Capability(
        "search_process",
        _search_process,
        "system",
        ("processes", "discovery", "application"),
        ("get_process",),
        ("processes", "application-discovery"),
    ),
    "get_user": Capability(
        "get_user", _get_user, "system", ("inventory",), ("get_session",), ("users",)
    ),
    "get_package": Capability(
        "get_package",
        _get_package,
        "system",
        ("inventory",),
        ("search_package",),
        ("packages",),
    ),
    "search_package": Capability(
        "search_package",
        _search_package,
        "system",
        ("packages", "discovery", "application"),
        ("get_package",),
        ("packages", "application-discovery"),
    ),
    "get_ssh": Capability(
        "get_ssh",
        _get_ssh,
        "security",
        ("ssh", "authentication"),
        ("get_firewall", "get_listening_ports"),
        ("ssh", "service_config"),
    ),
    "get_hardware": Capability(
        "get_hardware",
        _get_hardware,
        "system",
        ("inventory",),
        ("get_system",),
        ("hardware",),
    ),
    "get_pci": Capability(
        "get_pci", _get_pci, "system", ("inventory",), ("get_hardware",), ("hardware",)
    ),
    "get_usb": Capability(
        "get_usb", _get_usb, "system", ("inventory",), ("get_hardware",), ("hardware",)
    ),
    "get_gpu": Capability(
        "get_gpu",
        _get_gpu,
        "system",
        ("inventory",),
        ("get_hardware",),
        ("hardware", "gpu"),
    ),
    "get_block_device": Capability(
        "get_block_device",
        _get_block_device,
        "storage",
        ("storage",),
        ("get_disk",),
        ("storage", "block_device"),
    ),
    "get_secureboot": Capability(
        "get_secureboot",
        _get_secureboot,
        "security",
        ("security",),
        ("get_apparmor", "get_selinux"),
        ("secure-boot",),
    ),
    "get_apparmor": Capability(
        "get_apparmor",
        _get_apparmor,
        "security",
        ("security",),
        ("get_selinux", "get_firewall"),
        ("apparmor",),
    ),
    "get_selinux": Capability(
        "get_selinux",
        _get_selinux,
        "security",
        ("security",),
        ("get_apparmor",),
        ("selinux",),
    ),
    "get_firewall": Capability(
        "get_firewall",
        _get_firewall,
        "security",
        ("security", "firewall"),
        ("get_services", "get_listening_ports"),
        ("firewall", "firewall_status"),
    ),
    "get_certificate": Capability(
        "get_certificate",
        _get_certificate,
        "security",
        ("security",),
        ("get_ssh",),
        ("tls-certificates", "certificates"),
    ),
    "get_journal": Capability(
        "get_journal",
        _get_journal,
        "system",
        ("logs", "diagnostics"),
        ("get_log",),
        ("system-logs", "service_logs"),
    ),
    "get_log": Capability(
        "get_log",
        _get_log,
        "system",
        ("logs", "diagnostics"),
        ("get_journal",),
        ("system-logs",),
    ),
    "get_time": Capability(
        "get_time",
        _get_time,
        "system",
        ("time", "health"),
        ("get_time_sync", "get_uptime"),
        ("system-time",),
    ),
    "get_locale": Capability(
        "get_locale", _get_locale, "system", ("inventory",), (), ("system-locale",)
    ),
    "get_environment": Capability(
        "get_environment",
        _get_environment,
        "system",
        ("inventory",),
        (),
        ("system-environment", "env"),
    ),
    "get_session": Capability(
        "get_session",
        _get_session,
        "system",
        ("inventory",),
        ("get_recent_logins",),
        ("sessions",),
    ),
    "get_module": Capability(
        "get_module", _get_module, "system", ("inventory",), (), ("kernel-modules",)
    ),
    "get_lxd": Capability(
        "get_lxd",
        _get_lxd,
        "container",
        ("container",),
        ("get_docker",),
        ("container",),
    ),
    "get_uptime": Capability(
        "get_uptime",
        _get_uptime,
        "system",
        ("uptime", "health"),
        ("get_boot_time",),
        ("uptime",),
    ),
    "get_boot_time": Capability(
        "get_boot_time",
        _get_boot_time,
        "system",
        ("uptime",),
        ("get_uptime",),
        ("boot-time",),
    ),
    "get_cpu_usage": Capability(
        "get_cpu_usage",
        _get_cpu_usage,
        "system",
        ("cpu", "performance"),
        ("get_cpu", "get_system_load"),
        ("cpu", "cpu_usage"),
    ),
    "get_swap": Capability(
        "get_swap",
        _get_swap,
        "system",
        ("memory", "health"),
        ("get_memory",),
        ("swap",),
    ),
    "get_service": Capability(
        "get_service",
        _get_service,
        "system",
        ("services",),
        ("get_services", "search_service"),
        ("services",),
    ),
    "get_listening_ports": Capability(
        "get_listening_ports",
        _get_listening_ports,
        "network",
        ("network", "security"),
        ("search_process",),
        ("network", "listening-ports", "open_ports"),
    ),
    "get_disk_usage": Capability(
        "get_disk_usage",
        _get_disk_usage,
        "storage",
        ("storage", "health"),
        ("get_disk",),
        ("storage", "disk_usage"),
    ),
    "get_system_load": Capability(
        "get_system_load",
        _get_system_load,
        "system",
        ("load", "performance"),
        ("get_cpu", "get_memory"),
        ("load",),
    ),
    "get_recent_logins": Capability(
        "get_recent_logins",
        _get_recent_logins,
        "system",
        ("security",),
        ("get_session",),
        ("sessions",),
    ),
    "get_filesystem_health": Capability(
        "get_filesystem_health",
        _get_filesystem_health,
        "storage",
        ("storage", "health"),
        ("get_filesystem",),
        ("filesystem", "filesystem_discovery"),
    ),
    "get_time_sync": Capability(
        "get_time_sync",
        _get_time_sync,
        "system",
        ("time", "health"),
        ("get_time",),
        ("system-time",),
    ),
    "get_process_by_name": Capability(
        "get_process_by_name",
        _get_process_by_name,
        "system",
        ("processes", "discovery"),
        ("search_process", "get_process"),
        ("processes",),
    ),
}


class LinuxTool(Tool):
    """
    Tool con của KnowledgeTool, chịu trách nhiệm cho domain Linux.

    KnowledgeTool gọi execute() với một capability đã đặt tên (vd.
    "get_system"); LinuxTool không biết Agent, không biết Model, và
    không route sang Tool con khác. Một capability có thể chạy nhiều
    command và tự áp dụng fallback logic bên trong nó.

    Nếu capability không tồn tại, execute() trả về ToolResult thất bại
    kèm danh sách capability hợp lệ.

    Để thêm capability: viết một hàm trả về structured data, sau đó
    thêm một entry vào _CAPABILITIES. Không cần sửa gì khác.
    """

    def __init__(
        self,
        backend: ExecutionBackend | None = None,
    ) -> None:
        self._backend = backend or LocalExecutionBackend()

    def _run(
        self,
        command: list[str],
        timeout: int = 15,
    ) -> tuple[bool, str]:
        return self._backend.run(command, timeout=timeout)

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        action = arguments.get("action")
        request_id = arguments.get("request_id")

        if not isinstance(action, str):
            msg = "Missing action."
            raise ValueError(msg)

        host = getattr(self._backend, "_host", "localhost")

        info(
            "linux",
            request=request_id,
            capability=action,
            status="start",
            host=host,
            message="Executing",
        )
        _t0 = _time.monotonic()

        cap = _CAPABILITIES.get(action)

        if cap is None:
            available = ", ".join(sorted(_CAPABILITIES))
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "linux",
                request=request_id,
                capability=action,
                status="failed",
                error=f"Unknown action: '{action}'",
                host=host,
                message="Failed",
            )

            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'. Available actions: {available}.",
            )

        handler = cap.handler if isinstance(cap, Capability) else cap
        extra = {k: v for k, v in arguments.items() if k != "action"}
        sig = inspect.signature(handler)
        filtered: dict[str, object] = {}
        for k, v in extra.items():
            if k in sig.parameters:
                filtered[k] = v
            else:
                pass

        try:
            if filtered:
                data = handler(self._run, **filtered)
            else:
                data = handler(self._run)
        except Exception as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "linux",
                request=request_id,
                capability=action,
                status="failed",
                error=str(exc),
                host=host,
                message="Failed",
            )
            raise

        _dur = int((_time.monotonic() - _t0) * 1000)
        info(
            "linux",
            request=request_id,
            capability=action,
            status="success",
            duration_ms=_dur,
            host=host,
            message="Completed",
        )

        return ToolResult(
            success=True,
            data=data,
        )
