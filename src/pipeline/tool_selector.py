from __future__ import annotations

from enum import Enum, auto


class ToolCategory(Enum):
    """Tool categories for evidence collection."""

    LINUX = auto()
    GRAFANA = auto()
    ZABBIX = auto()
    KNOWLEDGE_BASE = auto()
    INTERNET = auto()


# Mapping from concept to preferred tool category.
# Some concepts can be served by multiple tools — this picks the best one.
_CONCEPT_TOOL_MAP: dict[str, ToolCategory] = {
    "cpu": ToolCategory.LINUX,
    "memory": ToolCategory.LINUX,
    "disk": ToolCategory.LINUX,
    "network": ToolCategory.LINUX,
    "hostname": ToolCategory.LINUX,
    "kernel": ToolCategory.LINUX,
    "uptime": ToolCategory.LINUX,
    "load": ToolCategory.LINUX,
    "performance": ToolCategory.LINUX,
    "service": ToolCategory.LINUX,
    "process": ToolCategory.LINUX,
    "package": ToolCategory.LINUX,
    "log": ToolCategory.LINUX,
    "container": ToolCategory.LINUX,
    "firewall": ToolCategory.LINUX,
    "ssh": ToolCategory.LINUX,
    "selinux": ToolCategory.LINUX,
    "apparmor": ToolCategory.LINUX,
    "alerts": ToolCategory.ZABBIX,
    "dashboards": ToolCategory.GRAFANA,
    "monitors": ToolCategory.ZABBIX,
    "gpu": ToolCategory.LINUX,
    "machine": ToolCategory.LINUX,
}

# User directives that override concept-based selection.
_TOOL_DIRECTIVES: dict[str, ToolCategory] = {
    "sử dụng grafana": ToolCategory.GRAFANA,
    "dùng grafana": ToolCategory.GRAFANA,
    "use grafana": ToolCategory.GRAFANA,
    "using grafana": ToolCategory.GRAFANA,
    "with grafana": ToolCategory.GRAFANA,
    "grafana": ToolCategory.GRAFANA,
    "sử dụng zabbix": ToolCategory.ZABBIX,
    "dùng zabbix": ToolCategory.ZABBIX,
    "use zabbix": ToolCategory.ZABBIX,
    "using zabbix": ToolCategory.ZABBIX,
    "with zabbix": ToolCategory.ZABBIX,
    "sử dụng linux": ToolCategory.LINUX,
    "dùng linux": ToolCategory.LINUX,
    "use linux": ToolCategory.LINUX,
    "internet": ToolCategory.INTERNET,
    "web": ToolCategory.INTERNET,
    "online": ToolCategory.INTERNET,
    "trực tuyến": ToolCategory.INTERNET,
}


class ToolSelector:
    """Select the best tool for evidence collection.

    Purely deterministic:
    1. Check for explicit user directives ("use grafana", "sử dụng zabbix").
    2. Map concept → preferred tool.
    """

    def select(
        self,
        raw_request: str,
        concept: str,
    ) -> ToolCategory:
        """Select the appropriate tool for the given request and concept.

        Args:
            raw_request: The original user request string.
            concept: The normalized concept from the Normalizer.

        Returns:
            The selected Tool enum.
        """
        lower = raw_request.lower()

        # 1. Explicit tool directives from user.
        for directive, tool in _TOOL_DIRECTIVES.items():
            if directive in lower:
                return tool

        # 2. Concept-based selection.
        if concept in _CONCEPT_TOOL_MAP:
            return _CONCEPT_TOOL_MAP[concept]

        # Default: Linux for infrastructure.
        return ToolCategory.LINUX
