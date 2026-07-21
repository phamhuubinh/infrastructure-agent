from __future__ import annotations

import inspect

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
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


class ZabbixTool(Tool):
    def __init__(self, url: str, token: str, timeout: int = 10) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        action = arguments.get("action")
        if not isinstance(action, str):
            return ToolResult(success=False, error="Missing action.")
        cap = _CAPABILITIES.get(action)
        if cap is None:
            available = ", ".join(sorted(_CAPABILITIES))
            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'. Available actions: {available}.",
            )
        handler = cap.handler if isinstance(cap, Capability) else cap
        api = _ZabbixAPI(url=self._url, token=self._token, timeout=self._timeout)
        extra = {key: value for key, value in arguments.items() if key != "action"}
        try:
            parameters = inspect.signature(handler).parameters
            data = handler(
                api, **{key: value for key, value in extra.items() if key in parameters}
            )
        except RuntimeError as exc:
            return ToolResult(success=False, error=str(exc))
        except TypeError as exc:
            return ToolResult(success=False, error=f"ZabbixTool error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, error=f"ZabbixTool error: {exc}")
        return ToolResult(success=True, data=data)


__all__ = ["ZabbixTool", "_CAPABILITIES"]
