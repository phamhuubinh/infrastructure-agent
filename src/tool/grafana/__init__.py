from __future__ import annotations

from urllib import parse as urllib_parse

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool

from .alerts import alert_rules
from .annotations import get_annotations
from .dashboards import (
    _dashboard_details,
    _dashboard_search,
    _dashboard_summary,
    _get_dashboards,
    _get_folders,
    _get_health,
    _get_version,
)
from .datasources import get_datasources
from .provider import GrafanaProvider

_CAPABILITIES: dict[str, Capability] = {
    "health": Capability(
        name="health",
        handler=_get_health,
        category="monitoring",
        intents=("monitor", "health"),
        related=("version",),
        covers=("monitoring-health",),
        description="Check if Grafana service is healthy and reachable",
        supported_targets=("grafana",),
        parameters=("source", "resource"),
        estimated_cost=0.05,
    ),
    "version": Capability(
        name="version",
        handler=_get_version,
        category="monitoring",
        intents=("monitor", "inventory"),
        related=("dashboards",),
        covers=("monitoring-version",),
        description="Get the Grafana server version",
        supported_targets=("grafana",),
        parameters=("source", "resource"),
        estimated_cost=0.05,
    ),
    "dashboards": Capability(
        name="dashboards",
        handler=_get_dashboards,
        category="monitoring",
        intents=("monitor", "inventory", "visualization"),
        related=("dashboard_search", "dashboard_summary"),
        covers=("dashboards",),
        description="List all dashboards from Grafana",
        supported_targets=("grafana",),
        parameters=("source", "resource"),
        estimated_cost=0.2,
    ),
    "dashboard_search": Capability(
        name="dashboard_search",
        handler=_dashboard_search,
        category="monitoring",
        intents=("monitor", "visualization", "inventory"),
        related=("dashboards",),
        covers=("dashboards",),
    ),
    "dashboard_summary": Capability(
        name="dashboard_summary",
        handler=_dashboard_summary,
        category="monitoring",
        intents=("monitor", "inventory", "overview"),
        related=("dashboards",),
        covers=("dashboards",),
    ),
    "dashboard_details": Capability(
        name="dashboard_details",
        handler=_dashboard_details,
        category="monitoring",
        intents=("monitor", "visualization", "investigation"),
        related=("dashboards",),
        covers=("dashboards", "panels", "queries"),
    ),
    "folders": Capability(
        name="folders",
        handler=_get_folders,
        category="monitoring",
        intents=("monitor", "inventory"),
        related=("dashboards",),
        covers=("monitoring-folders",),
    ),
    "datasources": Capability(
        name="datasources",
        handler=get_datasources,
        category="monitoring",
        intents=("monitor", "inventory", "connectivity"),
        related=("dashboards",),
        covers=("datasources",),
    ),
    "alert_rules": Capability(
        name="alert_rules",
        handler=alert_rules,
        category="monitoring",
        intents=("monitor", "alerts", "notification"),
        related=("health", "dashboards"),
        covers=("monitoring-alerts",),
    ),
    "annotations": Capability(
        name="annotations",
        handler=get_annotations,
        category="monitoring",
        intents=("monitor", "events", "timeline"),
        related=("dashboards",),
        covers=("monitoring-annotations",),
    ),
}


class GrafanaTool(Tool):
    def __init__(self, url: str, token: str, timeout: int = 10) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        try:
            api = GrafanaProvider(self._url, self._token, self._timeout)
            return self._dispatch(
                _CAPABILITIES,
                arguments,
                "GrafanaTool",
                provider=api,
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))

    def build_links(self, evidence_list: list, user_request: str) -> str:
        from src.shared.secrets import get_tool_config

        config = get_tool_config("grafana")
        grafana_url = config.get("url", "").rstrip("/") if config else ""
        if not grafana_url:
            return ""
        dashboards: list[tuple[object, object]] = []
        query_params: dict[object, object] = {}
        for package in evidence_list:
            if not getattr(package, "success", False) or package.evidence_name not in (
                "Dashboards",
                "Dashboard Discovery",
            ):
                continue
            data = package.data
            if not isinstance(data, dict):
                continue
            for item in (data.get("dashboards") or data.get("items") or [])[:5]:
                if isinstance(item, dict) and (uid := item.get("uid")):
                    dashboards.append(
                        (item.get("title") or item.get("name") or "Dashboard", uid)
                    )
            raw_params = data.get("query_params") or {}
            if isinstance(raw_params, dict):
                query_params.update(raw_params)
        if not dashboards:
            return ""
        raw = user_request.lower()
        signal = next(
            (
                name
                for name, matches in (
                    ("CPU", ("cpu",)),
                    ("Memory", ("memory", "ram")),
                    ("Network", ("network", "traffic")),
                    ("Disk", ("disk", "storage")),
                )
                if any(match in raw for match in matches)
            ),
            None,
        )
        lines = ["**Grafana Dashboards:**"]
        for title, uid in dashboards:
            params: dict[object, object] = {}
            if signal:
                params["var-signal"] = signal
            params.update(query_params)
            query = urllib_parse.urlencode(params) if params else ""
            url = f"{grafana_url}/d/{uid}"
            lines.append(
                f"- [{title}]({url}?{query})" if query else f"- [{title}]({url})"
            )
        return "\n".join(lines)
