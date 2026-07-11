from __future__ import annotations

from src.pipeline.capability_library import CAPABILITY_BY_EVIDENCE
from src.tool.knowledge_tool import KnowledgeTool


# ---------------------------------------------------------------------------
# Convention mapping: covers tag → operational capability name prefix
# ---------------------------------------------------------------------------
# This maps the short tags used in tool _CAPABILITIES[covers] to the
# operational capability names defined in capability_library.py.
#
# The mapping is derived from capability_library — it is NOT a second
# source of truth for capability definitions. It exists because tool
# metadata uses short tags (e.g. "cpu") while the pipeline uses
# operational names (e.g. "CPU Information").
#
# When a new operational capability is added to capability_library,
# an entry should be added here if no existing covers tag matches.

_COVERS_TO_OPERATIONAL: dict[str, str] = {
    # ---- Linux system ----
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
    "smart": "SMART Health Assessment",
    "raid": "RAID Health Assessment",
    # ---- Linux network ----
    "network": "Network Information",
    "interface": "Network Interface Discovery",
    "ip": "IP Configuration Assessment",
    "gateway": "Default Gateway Discovery",
    "dns": "DNS Configuration Assessment",
    "routing": "Routing Table Assessment",
    "listening-ports": "Port Discovery",
    "network_usage": "Network Utilization",
    # ---- Linux services & processes ----
    "services": "Service Status",
    "service_config": "Service Configuration Inspection",
    "service_logs": "Service Log Discovery",
    "dependencies": "Dependency Discovery",
    "processes": "Process Discovery",
    "packages": "Package Discovery",
    "container": "Container Discovery",
    # ---- Linux config & environment ----
    "config": "Configuration Inspection",
    "load": "System Load Assessment",
    "system-time": "Time Synchronization",
    "system-logs": "Log Discovery",
    "io": "I/O Performance Assessment",
    "env": "Environment Variable Discovery",
    # ---- Linux security ----
    "secure-boot": "Secure Boot Status",
    "apparmor": "AppArmor Status",
    "selinux": "SELinux Status",
    "ssh": "SSH Configuration Inspection",
    "firewall": "Firewall Inspection",
    "sessions": "Recent Login Discovery",
    "certificates": "Certificate Discovery",
    # ---- Zabbix monitoring ----
    "zabbix-problems": "Monitoring Problems",
    "zabbix-triggers": "Alert Triggers",
    "zabbix-hosts": "Host Status Assessment",
    "zabbix-events": "Event History Discovery",
    # ---- Grafana ----
    "dashboards": "Dashboard Discovery",
    "datasources": "Data Source Discovery",
}


class CapabilityRouter:
    """Resolve operational capability names to KnowledgeTool routes.

    Routes are built dynamically from KnowledgeTool metadata at
    construction time. The router itself contains no hardcoded
    capability definitions — it is a pure lookup layer over the
    metadata provided by registered Child Tools.

    Capability definitions have exactly one source of truth:
    the Child Tool _CAPABILITIES declarations.
    """

    def __init__(self) -> None:
        self._routes: dict[str, tuple[str, str]] = {}

    def build_routes(self, knowledge_tool: KnowledgeTool) -> None:
        """Build route table from KnowledgeTool capability metadata.

        Scans every registered tool/source, reads its capabilities,
        and maps each capability's covers tags to operational
        capability names using the convention mapping.

        Args:
            knowledge_tool: The KnowledgeTool instance with registered
                            Child Tools.
        """
        self._routes.clear()
        metadata = knowledge_tool.get_capability_metadata()

        for source, capabilities in metadata.items():
            for cap_info in capabilities:
                tool_cap_name = cap_info["name"]
                covers_list: list[str] = cap_info.get("covers", [])

                for covers_tag in covers_list:
                    op_name = _COVERS_TO_OPERATIONAL.get(covers_tag)
                    if op_name is None:
                        continue
                    # Only register if this operational capability exists in the library
                    if op_name not in CAPABILITY_BY_EVIDENCE.values() and \
                       op_name not in [v for v in CAPABILITY_BY_EVIDENCE.values()]:
                        continue
                    # Register route if not already registered (first source wins)
                    if op_name not in self._routes:
                        self._routes[op_name] = (source, tool_cap_name)

    def resolve(self, capability_name: str) -> tuple[str, str] | None:
        """Resolve an operational capability name to a KnowledgeTool route.

        Args:
            capability_name: The operational capability name.

        Returns:
            A (source, resource) tuple for KnowledgeTool dispatch,
            or None if no route is configured.
        """
        return self._routes.get(capability_name)

    def available_routes(self) -> list[str]:
        """Return all configured capability names."""
        return sorted(self._routes)

    @property
    def route_count(self) -> int:
        """Return the number of configured routes."""
        return len(self._routes)
