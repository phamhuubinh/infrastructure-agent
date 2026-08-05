from __future__ import annotations

from dataclasses import replace

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.errors import source_api_error
from src.tool.tool import Tool

from .client import _ZabbixAPI
from .events import (
    _get_event_summary,
    _get_events,
    _get_maintenance_status,
    _get_problem_timeline,
    _get_users,
)
from .history import _get_api_version, _get_items
from .hosts import (
    _get_host,
    _get_host_groups,
    _get_host_interfaces,
    _get_host_inventory,
    _get_hosts,
    _search_hosts,
)
from .templates import _get_templates
from .triggers import _get_problems, _get_triggers

_CAPABILITIES: dict[str, Capability] = {
    "get_api_version": Capability(
        "get_api_version",
        _get_api_version,
        "monitoring",
        ("monitor", "inventory"),
        ("get_hosts",),
        ("monitoring-version",),
        description="Retrieve the Zabbix API version",
        supported_targets=("zabbix",),
        parameters=("source", "resource"),
        estimated_cost=0.05,
    ),
    "get_hosts": Capability(
        "get_hosts",
        _get_hosts,
        "monitoring",
        ("monitor", "inventory"),
        ("get_problems", "get_triggers"),
        ("zabbix-hosts",),
        description="List all monitored hosts from Zabbix",
        supported_targets=("zabbix",),
        parameters=("source", "resource"),
        estimated_cost=0.2,
    ),
    "get_host": Capability(
        "get_host",
        _get_host,
        "monitoring",
        ("monitor", "inventory"),
        ("get_items",),
        ("zabbix-hosts",),
        description="Retrieve details for a specific Zabbix host",
        supported_targets=("zabbix",),
        parameters=("source", "resource", "host_id"),
        estimated_cost=0.1,
    ),
    "search_hosts": Capability(
        "search_hosts",
        _search_hosts,
        "monitoring",
        ("monitor", "inventory", "discovery"),
        ("get_host",),
        ("zabbix-hosts",),
    ),
    "get_host_groups": Capability(
        "get_host_groups",
        _get_host_groups,
        "monitoring",
        ("monitor", "inventory"),
        ("get_hosts",),
        ("zabbix-groups",),
    ),
    "get_templates": Capability(
        "get_templates",
        _get_templates,
        "monitoring",
        ("monitor", "inventory", "configuration"),
        ("get_hosts",),
        ("zabbix-templates",),
    ),
    "get_items": Capability(
        "get_items",
        _get_items,
        "monitoring",
        ("monitor", "inventory", "investigation"),
        ("get_triggers",),
        ("zabbix-items",),
    ),
    "get_triggers": Capability(
        "get_triggers",
        _get_triggers,
        "monitoring",
        ("monitor", "alerts"),
        ("get_problems", "get_events"),
        ("zabbix-triggers", "alert_severity"),
    ),
    "get_events": Capability(
        "get_events",
        _get_events,
        "monitoring",
        ("monitor", "events", "timeline"),
        ("get_problems",),
        ("zabbix-events",),
    ),
    "get_problems": Capability(
        "get_problems",
        _get_problems,
        "monitoring",
        ("monitor", "alerts", "incidents"),
        ("get_triggers", "get_events"),
        ("zabbix-problems",),
    ),
    "get_problem_timeline": Capability(
        "get_problem_timeline",
        _get_problem_timeline,
        "monitoring",
        ("monitor", "events", "timeline"),
        ("get_problems",),
        ("zabbix-events",),
    ),
    "get_host_inventory": Capability(
        "get_host_inventory",
        _get_host_inventory,
        "monitoring",
        ("monitor", "inventory"),
        ("get_hosts",),
        ("zabbix-hosts",),
    ),
    "get_host_interfaces": Capability(
        "get_host_interfaces",
        _get_host_interfaces,
        "monitoring",
        ("monitor", "inventory"),
        ("get_hosts",),
        ("zabbix-interfaces",),
    ),
    "get_maintenance_status": Capability(
        "get_maintenance_status",
        _get_maintenance_status,
        "monitoring",
        ("monitor", "maintenance"),
        ("get_hosts",),
        ("zabbix-maintenance",),
    ),
    "get_event_summary": Capability(
        "get_event_summary",
        _get_event_summary,
        "monitoring",
        ("monitor", "events", "timeline"),
        ("get_problems",),
        ("zabbix-events",),
    ),
    "get_users": Capability(
        "get_users",
        _get_users,
        "monitoring",
        ("monitor", "inventory"),
        (),
        ("zabbix-users",),
    ),
}

_PRODUCED_FACTS: dict[str, tuple[str, ...]] = {
    "get_items": ("monitoring.item",),
    "get_problems": ("monitoring.problem_active",),
    "get_problem_timeline": ("monitoring.problem_active",),
    "get_events": ("monitoring.event",),
    "get_event_summary": ("monitoring.event",),
    "get_hosts": ("monitoring.host_enabled",),
    "get_host": ("monitoring.host_enabled",),
    "search_hosts": ("monitoring.host_enabled",),
    "get_triggers": ("monitoring.trigger_active",),
}

for _name, _capability in tuple(_CAPABILITIES.items()):
    _CAPABILITIES[_name] = replace(
        _capability,
        produces_facts=_PRODUCED_FACTS.get(
            _name, (f"zabbix.{_name.removeprefix('get_')}",)
        ),
    )


class ZabbixTool(Tool):
    def __init__(self, url: str, token: str, timeout: int = 10) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        try:
            api = _ZabbixAPI(url=self._url, token=self._token, timeout=self._timeout)
            return self._dispatch(
                _CAPABILITIES,
                arguments,
                "ZabbixTool",
                provider=api,
            )
        except (RuntimeError, TypeError, ValueError, OSError) as exc:
            message = str(exc)
            return ToolResult(
                success=False,
                error=message,
                capability_error=source_api_error(message),
            )

    def build_links(
        self,
        evidence_list: list,
        user_request: str,
        time_range: tuple[int, int] | None = None,
    ) -> str:
        """Build bounded Zabbix links only from canonical provenance."""

        del user_request, time_range
        links: dict[str, str] = {}
        base = self._url.rstrip("/")
        for package in evidence_list:
            for fact in getattr(package, "facts", ()):
                provenance = getattr(fact, "provenance", None)
                if getattr(provenance, "source", None) != "zabbix":
                    continue
                reference = getattr(provenance, "source_reference", None)
                if not isinstance(reference, str) or not reference.startswith("/"):
                    continue
                href = f"{base}/{reference.lstrip('/')}"
                label = str(getattr(fact, "subject", getattr(fact, "metric", "Source")))
                label = label.replace("[", "(").replace("]", ")")[:100]
                links.setdefault(href, label)
        if not links:
            return ""
        lines = ["**Zabbix Sources:**"]
        lines.extend(
            f"- [{label}]({href})" for href, label in list(links.items())[:8]
        )
        return "\n".join(lines)


__all__ = ["ZabbixTool", "_CAPABILITIES"]
