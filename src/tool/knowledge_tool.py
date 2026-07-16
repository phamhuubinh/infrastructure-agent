from __future__ import annotations

import inspect

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.target_registry import TargetRegistry
from src.tool.tool import Tool


# ---------------------------------------------------------------------------
# Convention mapping: covers tag → operational capability name
# ---------------------------------------------------------------------------
# Single source of truth for mapping tool covers tags to operational
# pipeline capability names. Defined here because KnowledgeTool is the
# single aggregation point for tool metadata. All consumers
# (CapabilityRouter, etc.) should query this via KnowledgeTool.
#
# When a new operational capability is added, add an entry here.
# When a new tool covers tag maps to an existing operational name,
# no change needed.

_COVERS_TO_OPERATIONAL: dict[str, str] = {
    "system-identity": "System Information",
    "cpu": "CPU Information",
    "cpu_usage": "CPU Utilization",
    "memory": "Memory Information",
    "memory_usage": "Memory Utilization",
    "swap": "Swap Information",
    "storage": "Storage Information",
    "storage_performance": "Storage Performance Assessment",
    "filesystem": "Filesystem Information",
    "disk_usage": "Disk Utilization",
    "mount": "Mount Point Discovery",
    "filesystem_discovery": "Filesystem Discovery",
    "smart": "SMART Health Assessment",
    "raid": "RAID Health Assessment",
    "network": "Network Information",
    "interface": "Network Interface Discovery",
    "ip": "IP Configuration Assessment",
    "gateway": "Default Gateway Discovery",
    "dns": "DNS Configuration Assessment",
    "routing": "Routing Table Assessment",
    "listening-ports": "Port Discovery",
    "network_usage": "Network Utilization",
    "services": "Service Status",
    "service_config": "Service Configuration Inspection",
    "service_logs": "Service Log Discovery",
    "dependencies": "Dependency Discovery",
    "processes": "Process Discovery",
    "packages": "Package Discovery",
    "service_discovery": "Service Discovery",
    "container": "Container Discovery",
    "config": "Configuration Inspection",
    "load": "System Load Assessment",
    "system-time": "Time Synchronization",
    "system-logs": "Log Discovery",
    "io": "I/O Performance Assessment",
    "env": "Environment Variable Discovery",
    "secure-boot": "Secure Boot Status",
    "apparmor": "AppArmor Status",
    "selinux": "SELinux Status",
    "ssh": "SSH Configuration Inspection",
    "firewall": "Firewall Inspection",
    "sessions": "Recent Login Discovery",
    "certificates": "Certificate Discovery",
    "gpu": "GPU Information",
    "block_device": "Block Device Information",
    "firewall_status": "Firewall Status",
    "open_ports": "Listening Ports",
    "zabbix-problems": "Monitoring Problems",
    "zabbix-triggers": "Alert Triggers",
    "alert_severity": "Alert Severity Assessment",
    "zabbix-hosts": "Host Status Assessment",
    "zabbix-groups": "Host Group Discovery",
    "zabbix-templates": "Template Discovery",
    "zabbix-users": "Monitoring User Discovery",
    "zabbix-maintenance": "Maintenance Status Discovery",
    "zabbix-events": "Event History Discovery",
    "zabbix-interfaces": "Host Interface Discovery",
    "zabbix-items": "Item Discovery",
    "dashboards": "Dashboard Discovery",
    "monitoring-folders": "Dashboard Folder Discovery",
    "datasources": "Data Source Discovery",
    "monitoring-alerts": "Alert Rule Discovery",

    # Grafana — additional covers tags
    "monitoring-health": "Monitoring Health",
    "monitoring-version": "Monitoring Version",
    "panels": "Dashboard Panel Discovery",
    "queries": "Dashboard Query Discovery",
    "monitoring-annotations": "Monitoring Annotation Discovery",

    # Linux — additional covers tags
    "users": "User Discovery",
    "hardware": "Hardware Inventory",
    "uptime": "System Uptime",
    "boot-time": "System Boot Time",
    "kernel-modules": "Kernel Module Discovery",
    "system-locale": "System Locale Discovery",
    "system-environment": "Environment Variable Discovery",
    "tls-certificates": "Certificate Discovery",
    "application-discovery": "Service Discovery",
}


def _tool_capabilities(tool: Tool) -> list[str]:
    """Return the list of capability names exposed by a Tool module.

    Used by get_capabilities() for lightweight name-only discovery.
    The full metadata (covers, category, intents, related) is available
    via get_capability_metadata().
    """
    mod = inspect.getmodule(type(tool))
    if mod is not None and hasattr(mod, "_CAPABILITIES"):
        return list(mod._CAPABILITIES.keys())
    return []


class KnowledgeTool(Tool):
    """Single dispatch entry point for all infrastructure tool execution.

    KnowledgeTool owns exactly one responsibility: route a (source, resource)
    pair to the correct Child Tool registered in the TargetRegistry.

    It does NOT:
    - access infrastructure directly
    - execute shell commands
    - know about individual tool implementations
    - perform reasoning or assessment

    Adding a new infrastructure domain (Docker, VMware, ...):
    - Create a new Child Tool class
    - Register it in the TargetRegistry (via tools.json or directly)
    - No changes needed in KnowledgeTool
    """

    def __init__(
        self,
        target_registry: TargetRegistry | None = None,
    ) -> None:
        if target_registry is None:
            target_registry = TargetRegistry()
            target_registry.add("localhost")
        self._registry = target_registry

    @staticmethod
    def get_operational_name(covers_tag: str) -> str | None:
        """Resolve a covers tag to an operational capability name."""
        return _COVERS_TO_OPERATIONAL.get(covers_tag)

    def get_capabilities(self) -> dict[str, list[str]]:
        """Return mapping from target name to list of capability names.

        Lightweight discovery — returns only capability names.
        For full metadata (covers, category, intents), use
        get_capability_metadata().
        """
        caps: dict[str, list[str]] = {}
        for name in self._registry.target_names():
            tool = self._registry.get_tool(name)
            caps[name] = _tool_capabilities(tool)
        return caps

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        source = arguments.get("source")
        resource = arguments.get("resource")

        if not isinstance(source, str):
            raise ValueError("Missing source.")

        if not isinstance(resource, str):
            raise ValueError("Missing resource.")

        try:
            child_tool = self._registry.get_tool(source)
        except KeyError:
            available = ", ".join(self._registry.target_names())

            return ToolResult(
                success=False,
                error=f"Unknown source: '{source}'. Available sources: {available}.",
            )

        child_args: dict[str, object] = {"action": resource}
        extra = {k: v for k, v in arguments.items() if k not in ("source", "resource")}
        child_args.update(extra)

        return child_tool.execute(child_args)

    def get_capability_metadata(self) -> dict[str, list[dict[str, object]]]:
        """Return full capability metadata for every registered target.

        Each capability entry includes:
        - name: the capability identifier
        - category: functional category (system, network, storage, ...)
        - intents: related investigation intents
        - related: related capability names (dependency hints)
        - covers: convention tags for operational capability routing

        The handler field (implementation function) is intentionally
        excluded — it is an internal implementation detail of each tool.

        When a capability has multiple covers tags, each tag that resolves
        to an operational name produces a separate entry. This ensures
        multi-role capabilities (e.g., a trigger function that covers both
        "Alert Triggers" and "Alert Severity Assessment") register routes
        for all their operational names.
        """
        result: dict[str, list[dict[str, object]]] = {}
        for name in self._registry.target_names():
            tool = self._registry.get_tool(name)
            mod = inspect.getmodule(type(tool))
            if mod is None or not hasattr(mod, "_CAPABILITIES"):
                continue
            raw = getattr(mod, "_CAPABILITIES")
            entries: list[dict[str, object]] = []
            for cap_name, value in raw.items():
                if isinstance(value, Capability):
                    if value.operational_name:
                        entries.append({
                            "name": cap_name,
                            "category": value.category,
                            "intents": list(value.intents),
                            "related": list(value.related),
                            "covers": list(value.covers),
                            "operational_name": value.operational_name,
                        })
                    elif value.covers:
                        for tag in value.covers:
                            resolved = _COVERS_TO_OPERATIONAL.get(tag)
                            if resolved:
                                entries.append({
                                    "name": cap_name,
                                    "category": value.category,
                                    "intents": list(value.intents),
                                    "related": list(value.related),
                                    "covers": [tag],
                                    "operational_name": resolved,
                                })
                    else:
                        entries.append({"name": cap_name})
                else:
                    entries.append({"name": cap_name})
            if entries:
                result[name] = entries
        return result
