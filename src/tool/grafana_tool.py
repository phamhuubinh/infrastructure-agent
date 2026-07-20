from __future__ import annotations

import inspect
import json
from urllib import error as urlerror
from urllib import parse as urllib_parse
from urllib import request

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool


class GrafanaProvider:
    def __init__(self, url: str, token: str, timeout: int = 10) -> None:
        self._url = url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def get(self, path: str) -> object:
        try:
            req = request.Request(
                url=f"{self._url}{path}",
                headers=self._headers,
                method="GET",
            )
            with request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, urlerror.URLError, json.JSONDecodeError) as exc:
            msg = f"Grafana API request failed: {exc}"
            raise RuntimeError(msg) from exc


# ============================================================
# INFRASTRUCTURE TAXONOMY (deterministic classification only)
# ============================================================

_INFRA_DOMAINS: dict[str, str] = {
    "prometheus": "Monitoring",
    "zabbix": "Monitoring",
    "influxdb": "Monitoring",
    "graphite": "Monitoring",
    "elasticsearch": "Logging",
    "opensearch": "Logging",
    "loki": "Logging",
    "cloudwatch": "Cloud",
    "azuremonitor": "Cloud",
    "grafana": "Monitoring",
    "mysql": "Database",
    "postgres": "Database",
    "mssql": "Database",
    "jaeger": "Tracing",
    "tempo": "Tracing",
    "x-ray": "Tracing",
}


def _datasource_domain(ds_type: str) -> str:
    return _INFRA_DOMAINS.get(ds_type.lower(), "Unknown")


# ============================================================
# QUERY TYPE DETECTION (deterministic — pattern matching)
# ============================================================


def _detect_query_language(target: dict[str, object]) -> str:
    expr = target.get("expr", "")
    raw_query = target.get("rawQuery", "")
    query_type = ""
    if isinstance(expr, str) and expr.strip():
        query_type = "PromQL"
    elif isinstance(raw_query, str) and raw_query.strip():
        if "SELECT" in raw_query.upper() or "FROM" in raw_query.upper():
            query_type = "SQL"
        else:
            query_type = "RawQuery"
    ds_type = target.get("datasource", {})
    if isinstance(ds_type, dict):
        dt = ds_type.get("type", "")
        if dt == "__expr__" or target.get("type") == "expression":
            query_type = "Expression"
        elif dt == "mixed":
            query_type = "Mixed"
        elif dt == "grafana-annotations-datasource":
            query_type = "Annotations"
    return query_type


def _extract_metrics(target: dict[str, object]) -> list[str]:
    metrics: list[str] = []
    expr = target.get("expr")
    if isinstance(expr, str) and expr.strip():
        import re

        for m in re.findall(r"[a-zA-Z_][a-zA-Z0-9_:]+(?:\{[^}]*\})?", expr):
            metric_name = m.split("{")[0]
            if metric_name not in (
                "and",
                "or",
                "unless",
                "by",
                "without",
                "on",
                "ignoring",
                "group_left",
                "group_right",
                "offset",
            ):
                metrics.append(m)
    raw_query = target.get("rawQuery")
    if isinstance(raw_query, str) and raw_query.strip():
        metrics.append(raw_query[:120])
    query = target.get("query")
    if isinstance(query, str) and query.strip():
        metrics.append(query[:120])
    return metrics


# ============================================================
# QUERY EVIDENCE
# ============================================================


def _format_query(target: dict[str, object]) -> dict[str, object]:
    ds = target.get("datasource", {})
    ds_type = ""
    ds_uid = ""
    if isinstance(ds, dict):
        ds_type = ds.get("type", "")
        ds_uid = ds.get("uid", "")
    query_lang = _detect_query_language(target)
    metrics = _extract_metrics(target)
    return {
        "refId": target.get("refId", ""),
        "query_type": query_lang,
        "datasource_type": ds_type,
        "datasource_uid": ds_uid,
        "metrics": metrics,
        "legend_format": target.get("legendFormat", ""),
        "interval": target.get("interval", ""),
        "instant": target.get("instant", False),
        "range": target.get("range", True),
        "aggregation": target.get("aggregation", ""),
        "alias": target.get("alias", ""),
        "filters": target.get("filters", []),
    }


# ============================================================
# FIELD CONFIG EVIDENCE
# ============================================================


def _format_field_config(fc: object) -> dict[str, object]:
    if not isinstance(fc, dict):
        return {}
    defaults = fc.get("defaults", {})
    overrides = fc.get("overrides", [])
    if not isinstance(defaults, dict):
        defaults = {}
    if not isinstance(overrides, list):
        overrides = []
    thresholds = defaults.get("thresholds", {})
    mappings = defaults.get("mappings", [])
    custom = defaults.get("custom", {})
    if not isinstance(custom, dict):
        custom = {}
    color = defaults.get("color", {})
    return {
        "unit": defaults.get("unit", ""),
        "decimals": defaults.get("decimals"),
        "min": defaults.get("min"),
        "max": defaults.get("max"),
        "display_name": defaults.get("displayName", ""),
        "no_value": defaults.get("noValue", ""),
        "thresholds": thresholds if isinstance(thresholds, dict) else {},
        "mappings": mappings if isinstance(mappings, list) else [],
        "color_mode": color.get("mode", "") if isinstance(color, dict) else "",
        "custom_options": {
            k: v
            for k, v in custom.items()
            if not isinstance(v, (dict, list)) or len(str(v)) < 200
        },
        "override_count": len(overrides),
    }


# ============================================================
# TRANSFORMATIONS
# ============================================================


def _format_transformations(trans: object) -> list[dict[str, object]]:
    if not isinstance(trans, list):
        return []
    result: list[dict[str, object]] = []
    for t in trans:
        if not isinstance(t, dict):
            continue
        identity = t.get("id", "")
        options = t.get("options", {})
        result.append(
            {
                "id": identity,
                "options_summary": str(options)[:300]
                if isinstance(options, dict)
                else str(options)[:300],
            }
        )
    return result


# ============================================================
# PANEL EVIDENCE (recursive — supports nested rows/panels)
# ============================================================


def _format_panel(p: dict[str, object]) -> dict[str, object]:
    ds = p.get("datasource")
    ds_type = ""
    ds_uid = ""
    if isinstance(ds, dict):
        ds_type = ds.get("type", "")
        ds_uid = ds.get("uid", "")
    targets_raw = p.get("targets", [])
    targets = (
        [_format_query(t) for t in targets_raw if isinstance(t, dict)]
        if isinstance(targets_raw, list)
        else []
    )
    all_metrics: list[str] = []
    for t in targets:
        all_metrics.extend(t.get("metrics", []))
    field_config = _format_field_config(p.get("fieldConfig", {}))
    transformations = _format_transformations(p.get("transformations", []))
    grid_pos = p.get("gridPos", {})
    viz_type = p.get("type", "")
    viz_category = _visualization_category(viz_type)
    lib_panel = p.get("libraryPanel", {})
    links = p.get("links", [])
    result: dict[str, object] = {
        "id": p.get("id"),
        "title": p.get("title", ""),
        "description": p.get("description", ""),
        "type": viz_type,
        "visualization_category": viz_category,
        "plugin_version": p.get("pluginVersion", ""),
        "datasource_type": ds_type,
        "datasource_uid": ds_uid,
        "datasource_domain": _datasource_domain(ds_type),
        "transparent": p.get("transparent", False),
        "repeat": p.get("repeat", ""),
        "repeat_direction": p.get("repeatDirection", ""),
        "repeat_panel_id": p.get("repeatPanelId"),
        "grid_pos": {
            "h": grid_pos.get("h"),
            "w": grid_pos.get("w"),
            "x": grid_pos.get("x"),
            "y": grid_pos.get("y"),
        }
        if isinstance(grid_pos, dict)
        else {},
        "max_data_points": p.get("maxDataPoints"),
        "interval": p.get("interval", ""),
        "time_shift": p.get("timeShift", ""),
        "cache_timeout": p.get("cacheTimeout", ""),
        "links": links if isinstance(links, list) else [],
        "library_panel": {
            "uid": lib_panel.get("uid", ""),
            "name": lib_panel.get("name", ""),
        }
        if isinstance(lib_panel, dict)
        else {},
        "queries": targets,
        "metric_count": len(all_metrics),
        "metrics": all_metrics[:50],
        "field_config": field_config,
        "transformations": transformations,
        "observed_signals": _panel_signals(viz_type, all_metrics, field_config),
    }
    nested = p.get("panels")
    if isinstance(nested, list) and nested:
        result["nested_panels"] = [
            _format_panel(sp) for sp in nested if isinstance(sp, dict)
        ]
    collapsed = p.get("collapsed", False)
    if collapsed:
        result["collapsed"] = True
    return result


# ============================================================
# PANEL SIGNAL MAPPING (deterministic — no reasoning)
# ============================================================


def _panel_signals(
    viz_type: str, metrics: list[str], field_config: dict[str, object]
) -> list[str]:
    signals: list[str] = []
    unit = field_config.get("unit", "")
    full_text = " ".join(metrics).lower() + " " + unit.lower()
    if "cpu" in full_text or "cpu" in viz_type.lower():
        signals.append("CPU Utilization")
    if "memory" in full_text or "mem" in full_text:
        signals.append("Memory Utilization")
    if "disk" in full_text or "fs" in full_text or "filesystem" in full_text:
        signals.append("Disk Capacity")
    if (
        "network" in full_text
        or "net." in full_text
        or "traffic" in full_text
        or "throughput" in full_text
    ):
        signals.append("Network Throughput")
    if "latency" in full_text or "ping" in full_text or "response_time" in full_text:
        signals.append("Latency")
    if "packet" in full_text or "loss" in full_text:
        signals.append("Packet Loss")
    if "uptime" in full_text or "up{" in full_text or "up " in full_text:
        signals.append("Availability")
    if "temperature" in full_text or "temp" in full_text or "sensor" in full_text:
        signals.append("Temperature")
    if "error" in full_text or "error" in viz_type.lower():
        signals.append("Error Rate")
    if "request" in full_text or "requests" in full_text or "throughput" in full_text:
        signals.append("Request Rate")
    return signals


# ============================================================
# VISUALIZATION CATEGORY
# ============================================================


def _visualization_category(viz_type: str) -> str:
    cat_map: dict[str, str] = {
        "timeseries": "Time Series",
        "graph": "Time Series",
        "stat": "Stat",
        "gauge": "Gauge",
        "bargauge": "Bar Gauge",
        "table": "Table",
        "logs": "Logs",
        "statetimeline": "State Timeline",
        "state-timeline": "State Timeline",
        "heatmap": "Heatmap",
        "geomap": "Geomap",
        "nodegraph": "Node Graph",
        "node-graph": "Node Graph",
        "canvas": "Canvas",
        "piechart": "Pie Chart",
        "piechart-panel": "Pie Chart",
        "histogram": "Histogram",
        "text": "Text",
        "alertlist": "Alert List",
        "dashlist": "Dashboard List",
        "news": "News",
        "debug": "Debug",
        "row": "Row",
    }
    return cat_map.get(viz_type.lower(), "Other")


# ============================================================
# DASHBOARD EVIDENCE (full recursive extraction)
# ============================================================


def _extract_panels_recursive(
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in items:
        result.append(_format_panel(item))
        sub = item.get("panels")
        if isinstance(sub, list) and sub:
            result.extend(_extract_panels_recursive(sub))
    return result


def _dashboard_details(api: GrafanaProvider, uid: str = "") -> dict[str, object]:
    if not uid:
        return {"error": "Missing uid parameter."}
    result = api.get(f"/api/dashboards/uid/{uid}")
    if not isinstance(result, dict):
        return {"error": "Dashboard not found."}
    dashboard = result.get("dashboard", {})
    if not isinstance(dashboard, dict):
        return {"error": "Dashboard payload missing."}
    meta = result.get("meta", {})
    time = dashboard.get("time", {}) or {}
    links = dashboard.get("links", [])
    templating = dashboard.get("templating", {}) or {}
    annotations = dashboard.get("annotations", {}) or {}
    panels_raw = dashboard.get("panels", [])
    if not isinstance(panels_raw, list):
        panels_raw = []
    all_panels = _extract_panels_recursive(panels_raw)
    by_type: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    by_signal: dict[str, int] = {}
    all_signals: set[str] = set()
    for p in all_panels:
        t = p.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        dom = p.get("datasource_domain", "Unknown")
        by_domain[dom] = by_domain.get(dom, 0) + 1
        for sig in p.get("observed_signals", []):
            all_signals.add(sig)
            by_signal[sig] = by_signal.get(sig, 0) + 1
    variable_list = templating.get("list", [])
    annotation_list = annotations.get("list", [])
    return {
        "uid": uid,
        "title": dashboard.get("title", ""),
        "description": dashboard.get("description", ""),
        "version": dashboard.get("version"),
        "schema_version": dashboard.get("schemaVersion"),
        "folder_uid": meta.get("folderUid", dashboard.get("folderUid", "")),
        "folder_title": meta.get("folderTitle", dashboard.get("folderTitle", "")),
        "tags": dashboard.get("tags", []),
        "timezone": dashboard.get("timezone", ""),
        "editable": dashboard.get("editable", True),
        "graph_tooltip": dashboard.get("graphTooltip", 0),
        "refresh": dashboard.get("refresh", ""),
        "week_start": dashboard.get("weekStart", ""),
        "live_now": dashboard.get("liveNow", False),
        "time_from": time.get("from", ""),
        "time_to": time.get("to", ""),
        "links": [
            {
                "title": link.get("title", ""),
                "type": link.get("type", ""),
                "url": link.get("url", ""),
            }
            for link in links
            if isinstance(link, dict)
        ],
        "variables": [
            {
                "name": v.get("name", ""),
                "type": v.get("type", ""),
                "query": v.get("query", ""),
                "definition": v.get("definition", ""),
                "datasource": v.get("datasource", ""),
                "include_all": v.get("includeAll", False),
                "multi": v.get("multi", False),
            }
            for v in variable_list
            if isinstance(v, dict)
        ],
        "annotations_definitions": [
            {
                "name": a.get("name", ""),
                "datasource": a.get("datasource", {}).get("uid", ""),
                "enable": a.get("enable", True),
                "iconColor": a.get("iconColor", ""),
            }
            for a in annotation_list
            if isinstance(a, dict)
        ],
        "total_panels": len(all_panels),
        "panels": all_panels,
        "panel_type_summary": by_type,
        "datasource_domain_summary": by_domain,
        "observed_signals": sorted(all_signals),
        "observed_signal_summary": by_signal,
        "infrastructure_domains": sorted(set(by_domain.keys())),
    }


# ============================================================
# EXISTING CAPABILITIES (unchanged except datasources extended)
# ============================================================


def _format_dashboard(d: dict[str, object]) -> dict[str, object]:
    return {
        "title": d.get("title", ""),
        "uid": d.get("uid", ""),
        "folder": d.get("folderTitle", d.get("folderUid", "")),
        "tags": d.get("tags", []),
        "url": d.get("url", ""),
    }


def _get_health(api: GrafanaProvider) -> dict[str, object]:
    return {"health": api.get("/api/health")}


def _get_version(api: GrafanaProvider) -> dict[str, object]:
    admin = api.get("/api/admin/stats")
    if isinstance(admin, dict) and "version" in admin:
        return {"version": admin["version"]}
    frontend = api.get("/api/frontend/settings")
    if isinstance(frontend, dict):
        return {"version": frontend.get("buildInfo", {}).get("version", "unknown")}
    return {"version": "unknown"}


def _get_dashboards(api: GrafanaProvider) -> dict[str, object]:
    result = api.get("/api/search")
    if not isinstance(result, list):
        return {"dashboards": [], "total": 0}
    dashboards = [_format_dashboard(d) for d in result if isinstance(d, dict)]
    return {"dashboards": dashboards, "total": len(dashboards)}


def _dashboard_search(api: GrafanaProvider, query: str = "") -> dict[str, object]:
    params = f"?query={urllib_parse.quote(query)}" if query else ""
    result = api.get(f"/api/search{params}")
    if not isinstance(result, list):
        return {"dashboards": [], "total": 0}
    dashboards = [_format_dashboard(d) for d in result if isinstance(d, dict)]
    return {"dashboards": dashboards, "total": len(dashboards)}


def _dashboard_summary(api: GrafanaProvider) -> dict[str, object]:
    result = api.get("/api/search")
    if not isinstance(result, list):
        return {"total": 0, "total_tags": 0, "dashboards_with_errors": 0}
    total = len(result)
    tags: set[str] = set()
    for d in result:
        if isinstance(d, dict):
            for t in d.get("tags", []):
                if isinstance(t, str):
                    tags.add(t)
    tag_count = len(tags)
    return {
        "total": total,
        "total_tags": tag_count,
        "tag_list": sorted(tags) if tags else [],
    }


def _get_folders(api: GrafanaProvider) -> dict[str, object]:
    result = api.get("/api/folders")
    if not isinstance(result, list):
        return {"folders": [], "total": 0}
    folders = [
        {"uid": f.get("uid", ""), "title": f.get("title", ""), "url": f.get("url", "")}
        for f in result
        if isinstance(f, dict)
    ]
    return {"folders": folders, "total": len(folders)}


def _get_datasources(api: GrafanaProvider) -> dict[str, object]:
    result = api.get("/api/datasources")
    if not isinstance(result, list):
        return {"datasources": [], "total": 0}
    ds = [
        {
            "name": d.get("name", ""),
            "type": d.get("type", ""),
            "url": d.get("url", ""),
            "is_default": d.get("isDefault", False),
            "uid": d.get("uid", ""),
            "database": d.get("database", ""),
            "user": d.get("user", ""),
            "access": d.get("access", ""),
            "basic_auth": d.get("basicAuth", False),
            "domain": _datasource_domain(d.get("type", "")),
        }
        for d in result
        if isinstance(d, dict)
    ]
    return {"datasources": ds, "total": len(ds)}


def _alert_rules(api: GrafanaProvider) -> dict[str, object]:
    result = api.get("/api/v1/provisioning/alert-rules")
    if not isinstance(result, list):
        return {"alert_rules": [], "total": 0}
    rules = []
    for r in result:
        if not isinstance(r, dict):
            continue
        rules.append(
            {
                "uid": r.get("uid", ""),
                "title": r.get("title", ""),
                "folder": r.get("folderUID", ""),
                "interval": r.get("intervalSeconds"),
                "for": r.get("for"),
            }
        )
    return {"alert_rules": rules, "total": len(rules)}


def _get_annotations(api: GrafanaProvider, limit: int = 50) -> dict[str, object]:
    result = api.get(f"/api/annotations?limit={limit}")
    if not isinstance(result, list):
        return {"annotations": [], "total": 0}
    annotations = [
        {
            "id": a.get("id"),
            "text": a.get("text", ""),
            "dashboard_uid": a.get("dashboardUID", ""),
            "panel_id": a.get("panelId"),
            "created": a.get("created"),
            "updated": a.get("updated"),
        }
        for a in result
        if isinstance(a, dict)
    ]
    return {"annotations": annotations, "total": len(annotations)}


# ============================================================
# CAPABILITIES REGISTRY
# ============================================================

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
        handler=_get_datasources,
        category="monitoring",
        intents=("monitor", "inventory", "connectivity"),
        related=("dashboards",),
        covers=("datasources",),
    ),
    "alert_rules": Capability(
        name="alert_rules",
        handler=_alert_rules,
        category="monitoring",
        intents=("monitor", "alerts", "notification"),
        related=("health", "dashboards"),
        covers=("monitoring-alerts",),
    ),
    "annotations": Capability(
        name="annotations",
        handler=_get_annotations,
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

        api = GrafanaProvider(url=self._url, token=self._token, timeout=self._timeout)
        extra = {k: v for k, v in arguments.items() if k != "action"}

        try:
            sig = inspect.signature(handler)
            filtered: dict[str, object] = {}
            for k, v in extra.items():
                if k in sig.parameters:
                    filtered[k] = v
                else:
                    pass
            data = handler(api, **filtered)
        except RuntimeError as exc:
            return ToolResult(success=False, error=str(exc))
        except TypeError as exc:
            return ToolResult(success=False, error=f"GrafanaTool error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, error=f"GrafanaTool error: {exc}")

        return ToolResult(success=True, data=data)

    def build_links(
        self,
        evidence_list: list,
        user_request: str,
    ) -> str:
        from src.shared.secrets import get_tool_config

        config = get_tool_config("grafana")
        if not config:
            return ""

        grafana_url = config.get("url", "").rstrip("/")
        if not grafana_url:
            return ""

        dashboards = []
        query_params = {}
        for pkg in evidence_list:
            if not hasattr(pkg, "success") or not pkg.success:
                continue
            if pkg.evidence_name in ("Dashboards", "Dashboard Discovery"):
                data = pkg.data
                if isinstance(data, dict):
                    items = data.get("dashboards") or data.get("items") or []
                    if isinstance(items, list):
                        for item in items[:5]:
                            if isinstance(item, dict):
                                uid = item.get("uid") or ""
                                title = (
                                    item.get("title") or item.get("name") or "Dashboard"
                                )
                                if uid:
                                    dashboards.append((title, uid))
                    raw_params = data.get("query_params") or {}
                    if isinstance(raw_params, dict):
                        query_params.update(raw_params)
        if not dashboards:
            return ""

        raw = user_request.lower()
        is_cpu = "cpu" in raw
        is_mem = any(kw in raw for kw in ("memory", "ram"))
        is_net = any(kw in raw for kw in ("network", "traffic"))
        is_disk = any(kw in raw for kw in ("disk", "storage"))

        lines = ["**Grafana Dashboards:**"]
        for title, uid in dashboards:
            base_url = f"{grafana_url}/d/{uid}"
            params = {}
            if is_cpu:
                params["var-signal"] = "CPU"
            elif is_mem:
                params["var-signal"] = "Memory"
            elif is_net:
                params["var-signal"] = "Network"
            elif is_disk:
                params["var-signal"] = "Disk"

            raw_params = query_params
            if isinstance(raw_params, dict):
                params.update(raw_params)

            qs = urllib_parse.urlencode(params) if params else ""
            url = f"{base_url}?{qs}" if qs else base_url
            lines.append(f"- [{title}]({url})")

        return "\n".join(lines)
