from __future__ import annotations

import inspect
import time as _time
from dataclasses import replace

from src.shared.capability import Capability, ParameterSpec
from src.shared.execution.command_result import CommandResult, CommandStatus
from src.shared.execution.tool_result import ToolResult
from src.shared.logger import error, info
from src.tool.capability_result import CapabilityResult, CapabilityStatus
from src.tool.errors import internal_error
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
    _get_disk_device_health,
    _get_disk_io,
    _get_disk_usage,
    _get_filesystem,
    _get_filesystem_health,
    _get_filesystem_inode,
)
from .capabilities.memory import _get_memory, _get_swap
from .capabilities.network import (
    _get_bandwidth,
    _get_dns,
    _get_interface_stats,
    _get_listening_ports,
    _get_network,
    _get_ping_latency,
)
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
    _get_service_logs,
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
from .output_schema import validate_linux_output

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
        ("system-logs",),
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
    "get_interface_stats": Capability(
        "get_interface_stats",
        _get_interface_stats,
        "network",
        ("network", "performance", "diagnostics"),
        ("get_network",),
        ("network", "interface_stats", "traffic", "packet_loss"),
        description="Per-interface traffic statistics (bytes/packets/errors/drops)",
        supported_targets=("localhost",),
        parameters=("source", "resource"),
        estimated_cost=0.1,
    ),
    "get_bandwidth": Capability(
        "get_bandwidth",
        _get_bandwidth,
        "network",
        ("network", "performance"),
        ("get_network", "get_interface_stats"),
        ("network", "bandwidth", "throughput"),
        description="Current bandwidth usage via sar (requires sysstat)",
        supported_targets=("localhost",),
        parameters=("source", "resource"),
        estimated_cost=0.3,
    ),
    "get_ping_latency": Capability(
        "get_ping_latency",
        _get_ping_latency,
        "network",
        ("network", "diagnostics", "connectivity"),
        ("get_network",),
        ("network", "latency", "ping"),
        description="Ping latency to a specific target (only on explicit request)",
        supported_targets=("localhost",),
        parameters=("source", "resource", "target"),
        estimated_cost=1.0,
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
    "get_service_logs": Capability(
        "get_service_logs",
        _get_service_logs,
        "system",
        ("logs", "services", "diagnostics"),
        ("get_service",),
        ("service_logs",),
        description="Collect bounded logs for one validated service and time range",
    ),
    "get_filesystem_inode": Capability(
        "get_filesystem_inode",
        _get_filesystem_inode,
        "storage",
        ("storage", "capacity"),
        ("get_disk",),
        ("filesystem_inode",),
        description="Collect per-filesystem inode capacity and utilization",
    ),
    "get_disk_io": Capability(
        "get_disk_io",
        _get_disk_io,
        "storage",
        ("storage", "performance"),
        ("get_disk",),
        ("disk_io",),
        description="Collect cumulative block-device I/O counters",
    ),
    "get_disk_device_health": Capability(
        "get_disk_device_health",
        _get_disk_device_health,
        "storage",
        ("storage", "health"),
        ("get_block_device",),
        ("disk_health",),
        description="Collect SMART or NVMe health without inferring from capacity",
    ),
}


_PRODUCED_FACTS: dict[str, tuple[str, ...]] = {
    "get_cpu": ("cpu.identity", "cpu.logical_cores", "cpu.usage", "system.load"),
    "get_cpu_usage": ("cpu.usage",),
    "get_system_load": ("system.load",),
    "get_memory": ("memory.capacity", "memory.usage", "swap.capacity"),
    "get_swap": ("swap.capacity", "swap.usage"),
    "get_disk": ("filesystem.capacity",),
    "get_disk_usage": ("filesystem.capacity",),
    "get_filesystem": ("filesystem.mount",),
    "get_filesystem_inode": ("filesystem.inode",),
    "get_disk_io": ("disk.io",),
    "get_disk_device_health": ("disk.device_health",),
    "get_filesystem_health": ("filesystem.mount_state",),
    "get_network": ("network.interface", "network.route"),
    "get_interface_stats": ("network.interface_stats",),
    "get_listening_ports": ("network.listening_socket",),
    "get_services": ("service.inventory", "service.state"),
    "get_service": ("service.state",),
    "get_service_logs": ("service.log",),
    "get_journal": ("system.log",),
}

_REQUIRED_BINARIES: dict[str, tuple[str, ...]] = {
    "get_bandwidth": ("sar",),
    "get_block_device": ("lsblk",),
    "get_disk": ("df",),
    "get_disk_usage": ("df",),
    "get_filesystem_inode": ("df",),
    "get_ping_latency": ("ping",),
    "get_hardware": ("dmidecode",),
    "get_pci": ("lspci",),
    "get_gpu": ("lspci",),
    "get_usb": ("lsusb",),
}

_OPTIONAL_BINARIES: dict[str, tuple[str, ...]] = {
    "get_disk_device_health": ("smartctl", "nvme"),
    "get_disk_io": ("iostat",),
    "get_firewall": ("ufw", "iptables", "nft"),
    "get_cpu": ("lscpu", "top"),
}

_REQUIRED_ANY_BINARIES: dict[str, tuple[str, ...]] = {
    "get_disk_device_health": ("smartctl", "nvme"),
    "get_firewall": ("ufw", "iptables", "nft"),
    "get_service": ("systemctl", "service", "rc-service", "pgrep", "ss"),
    "get_services": ("systemctl", "service", "rc-status", "ps"),
    "get_service_logs": ("journalctl", "tail"),
}

_PARAMETERS: dict[str, tuple[str, ...]] = {
    "get_service": ("name",),
    "search_service": ("query",),
    "get_service_logs": ("service_name", "time_range", "since", "until", "limit"),
    "get_journal": ("service_name", "time_range"),
    "get_process_by_name": ("name",),
    "search_process": ("query",),
    "get_ping_latency": ("target", "count"),
    "get_disk": ("path",),
    "get_disk_usage": ("path",),
    "get_filesystem": ("path",),
    "get_listening_ports": ("port",),
}

_SERVICE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$"
_HOST_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,253}$"
_PATH_PATTERN = r"^/(?:[A-Za-z0-9._-]+/?)*$"
_PARAMETER_SPECS: dict[str, tuple[ParameterSpec, ...]] = {
    "get_service": (
        ParameterSpec("name", source="service_name", required=True, pattern=_SERVICE_PATTERN),
    ),
    "search_service": (
        ParameterSpec("query", source="service_name", required=True, pattern=_SERVICE_PATTERN),
    ),
    "get_service_logs": (
        ParameterSpec(
            "service_name", source="service_name", required=True, pattern=_SERVICE_PATTERN
        ),
        ParameterSpec("time_range", source="time_range"),
        ParameterSpec("since", source="timeframe.start", value_type="int"),
        ParameterSpec("until", source="timeframe.end", value_type="int"),
        ParameterSpec(
            "limit", source="limit", value_type="int", default=50, has_default=True,
            minimum=1, maximum=500
        ),
    ),
    "get_journal": (
        ParameterSpec("service_name", source="service_name", pattern=_SERVICE_PATTERN),
        ParameterSpec("time_range", source="time_range"),
    ),
    "get_process_by_name": (
        ParameterSpec("name", source="process_name", required=True, pattern=_SERVICE_PATTERN),
    ),
    "search_process": (
        ParameterSpec("query", source="process_name", required=True, pattern=_SERVICE_PATTERN),
    ),
    "get_ping_latency": (
        ParameterSpec("target", source="ping_target", required=True, pattern=_HOST_PATTERN),
        ParameterSpec(
            "count", source="count", value_type="int", default=4, has_default=True,
            minimum=1, maximum=10
        ),
    ),
    "get_disk": (ParameterSpec("path", source="path", pattern=_PATH_PATTERN),),
    "get_disk_usage": (ParameterSpec("path", source="path", pattern=_PATH_PATTERN),),
    "get_filesystem": (ParameterSpec("path", source="path", pattern=_PATH_PATTERN),),
    "get_listening_ports": (
        ParameterSpec("port", source="port", value_type="int", minimum=1, maximum=65535),
    ),
}

# Enrich declarations in one place. KnowledgeTool only aggregates this
# metadata and never maintains a second capability policy table.
_ALTERNATIVES = {
    "get_cpu_usage": ("CPU Information",),
    "get_system_load": ("CPU Information",),
    "get_swap": ("Memory Information",),
    "get_disk_usage": ("Storage Information",),
}
_ALTERNATIVE_ERRORS = (
    "command_not_found",
    "unsupported_environment",
    "parse_error",
)
for _name, _capability in tuple(_CAPABILITIES.items()):
    _CAPABILITIES[_name] = replace(
        _capability,
        supported_targets=("local", "ssh"),
        parameters=_PARAMETERS.get(_name, _capability.parameters),
        parameter_specs=_PARAMETER_SPECS.get(_name, ()),
        preconditions=("linux",),
        required_binaries=_REQUIRED_BINARIES.get(_name, ()),
        required_any_binaries=_REQUIRED_ANY_BINARIES.get(_name, ()),
        optional_binaries=_OPTIONAL_BINARIES.get(_name, ()),
        expected_reliability=(
            0.7
            if _name == "get_disk_device_health"
            else 0.8
            if _name in {"get_service_logs", "get_services", "get_service"}
            else 0.9
        ),
        produces_facts=_PRODUCED_FACTS.get(
            _name, (f"linux.{_name.removeprefix('get_')}",)
        ),
        alternatives=_ALTERNATIVES.get(_name, ()),
        recoverable_errors=(
            _ALTERNATIVE_ERRORS if _name in _ALTERNATIVES else ()
        ),
        mutation_risk="none",
    )


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
        target_identity: dict[str, str] | None = None,
    ) -> None:
        self._backend = backend or LocalExecutionBackend()
        self._target_identity = dict(target_identity) if target_identity else None

    def _run(
        self,
        command: list[str],
        timeout: int = 15,
    ) -> CommandResult:
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
                capability_status=CapabilityStatus.INVALID_PARAMETERS,
            )

        handler = cap.handler if isinstance(cap, Capability) else cap
        extra = {k: v for k, v in arguments.items() if k != "action"}
        sig = inspect.signature(handler)
        filtered: dict[str, object] = {}
        unexpected = sorted(
            key
            for key in extra
            if key not in sig.parameters and key not in {"request_id"}
        )
        if unexpected:
            return ToolResult(
                success=False,
                error=(
                    f"Invalid parameter(s) for capability '{action}': "
                    f"{', '.join(unexpected)}"
                ),
                capability_status=CapabilityStatus.INVALID_PARAMETERS,
            )
        for k, v in extra.items():
            if k in sig.parameters:
                filtered[k] = v
            else:
                pass

        command_results: list[CommandResult] = []
        legacy_command_results: list[CommandResult] = []

        def tracked_run(command: list[str], timeout: int = 15):
            result = self._run(command, timeout=timeout)
            if isinstance(result, CommandResult):
                command_results.append(result)
            elif (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[0], bool)
                and isinstance(result[1], str)
            ):
                # Temporary compatibility backends and tests still return the
                # historical ``(ok, output)`` pair.  Record that outcome too,
                # otherwise a failed legacy command can be wrapped as VALID
                # merely because its handler manufactured a default payload.
                ok, output = result
                legacy_command_results.append(
                    CommandResult(
                        status=(
                            CommandStatus.SUCCESS
                            if ok and output
                            else CommandStatus.EMPTY_SUCCESS
                            if ok
                            else CommandStatus.NON_ZERO_EXIT
                        ),
                        exit_code=0 if ok else None,
                        stdout=output if ok else "",
                        stderr="" if ok else output,
                        error_type=None if ok else "LegacyCommandFailure",
                        command_id=f"legacy:{command[0] if command else 'empty'}",
                        target=str(host),
                    )
                )
            return result

        try:
            if filtered:
                output = handler(tracked_run, **filtered)
            else:
                output = handler(tracked_run)
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
            message = f"Error executing capability '{action}': {exc}"
            return ToolResult(
                success=False,
                error=message,
                capability_status=CapabilityStatus.COLLECTION_FAILED,
                command_results=tuple(command_results),
                capability_error=internal_error(message),
                produced_fact_names=cap.produces_facts,
            )

        # Legacy tuple adapters cannot declare intentional fallback attempts.
        # If at least one legacy command succeeded, retain only those successes
        # and let handlers omit fields from failed optional probes.  If every
        # attempt failed, retain them all so manufactured defaults cannot pass.
        effective_command_results = tuple(command_results)
        if not effective_command_results and legacy_command_results:
            legacy_successes = tuple(
                result for result in legacy_command_results if result.success
            )
            effective_command_results = legacy_successes or tuple(
                legacy_command_results
            )

        if isinstance(output, CapabilityResult):
            capability_result = output
            if not capability_result.command_results:
                capability_result = replace(
                    capability_result,
                    command_results=effective_command_results,
                )
            if not capability_result.produced_fact_names:
                capability_result = replace(
                    capability_result,
                    produced_fact_names=cap.produces_facts,
                )
        else:
            capability_result = CapabilityResult.from_legacy(
                output,
                command_results=effective_command_results,
                produced_fact_names=cap.produces_facts,
                warn_legacy=False,
            )

        if isinstance(capability_result.data, dict):
            payload = dict(capability_result.data)
            if self._target_identity is not None:
                payload["target_identity"] = dict(self._target_identity)
            if capability_result.status in (
                CapabilityStatus.VALID,
                CapabilityStatus.VALID_EMPTY,
            ):
                violations = validate_linux_output(action, payload)
                if violations:
                    capability_result = CapabilityResult(
                        status=CapabilityStatus.PARSE_FAILED,
                        data=None,
                        command_results=capability_result.command_results,
                        warnings=capability_result.warnings,
                        produced_fact_names=cap.produces_facts,
                        error=(
                            f"Linux capability output failed schema validation: "
                            f"{'; '.join(violations)}"
                        ),
                    )
                elif payload != capability_result.data:
                    capability_result = replace(capability_result, data=payload)
            elif payload != capability_result.data:
                capability_result = replace(capability_result, data=payload)

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

        return ToolResult.from_capability_result(capability_result)
