from __future__ import annotations

import json
from collections.abc import Callable
from urllib import error as urlerror
from urllib import request

from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool


SEVERITY_LABELS = {"0": "ok", "1": "info", "2": "warning", "3": "average", "4": "high", "5": "disaster"}


class _ZabbixAPI:
    def __init__(self, url: str, token: str, timeout: int = 10) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._request_id = 0

    def call(self, method: str, params: dict[str, object] | None = None, skip_auth: bool = False) -> object:
        self._request_id += 1
        payload: dict[str, object] = {
            "jsonrpc": "2.0", "method": method, "params": params or {}, "id": self._request_id,
        }
        if not skip_auth:
            payload["auth"] = self._token

        headers = {"Content-Type": "application/json-rpc"}
        body = json.dumps(payload).encode("utf-8")

        try:
            req = request.Request(url=f"{self._url}/api_jsonrpc.php", data=body, headers=headers, method="POST")
            with request.urlopen(req, timeout=self._timeout) as resp:
                data: dict[str, object] = json.loads(resp.read().decode("utf-8"))
        except (OSError, urlerror.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Zabbix API request failed: {exc}") from exc

        error = data.get("error")
        if error is not None:
            msg = error.get("message", "unknown")
            detail = error.get("data", "")
            raise RuntimeError(f"Zabbix API error: {msg} - {detail}")

        result = data.get("result")
        if result is None:
            raise RuntimeError("Zabbix API returned no result.")
        return result


def _severity_label(pri: object) -> str:
    return SEVERITY_LABELS.get(str(pri), "unknown")


def _count_by_severity(items: list[dict[str, object]], key: str = "severity") -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        s = str(item.get(key, "0"))
        lbl = _severity_label(s)
        counts[lbl] = counts.get(lbl, 0) + 1
    return counts


# ============================================================
# EXISTING CAPABILITIES — ENRICHED
# ============================================================

def _get_api_version(zapi: _ZabbixAPI) -> dict[str, object]:
    return {"version": zapi.call("apiinfo.version", skip_auth=True)}


def _format_host(h: dict[str, object]) -> dict[str, object]:
    groups = h.get("groups")
    interfaces = h.get("interfaces")
    group_names = ", ".join(
        g.get("name", "") for g in groups if isinstance(g, dict)
    ) if isinstance(groups, list) else ""
    ips = ", ".join(
        i.get("ip", "") for i in interfaces if isinstance(i, dict)
    ) if isinstance(interfaces, list) else ""
    return {
        "hostid": h.get("hostid"), "host": h.get("host"), "name": h.get("name"),
        "status": h.get("status"), "groups": group_names, "ip": ips,
    }


def _get_hosts(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("host.get", {
        "output": ["hostid", "host", "name", "status"],
        "selectGroups": ["groupid", "name"],
        "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
    })
    if not isinstance(result, list):
        return {"hosts": [], "total_hosts": 0}
    hosts = [_format_host(h) for h in result if isinstance(h, dict)]
    enabled = sum(1 for h in hosts if h.get("status") == "0")
    return {
        "hosts": hosts, "total_hosts": len(hosts),
        "enabled_hosts": enabled, "disabled_hosts": len(hosts) - enabled,
    }


def _get_host(zapi: _ZabbixAPI, host: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["hostid", "host", "name", "status"],
        "selectGroups": ["groupid", "name"],
        "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
    }
    if host:
        if host.isdigit():
            params["hostids"] = host
        else:
            params["filter"] = {"host": host}
    result = zapi.call("host.get", params)
    if not isinstance(result, list):
        return {"hosts": []}
    return {"hosts": [_format_host(h) for h in result if isinstance(h, dict)]}


def _get_host_groups(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("hostgroup.get", {"output": ["groupid", "name"]})
    if not isinstance(result, list):
        return {"groups": []}
    return {"groups": [g for g in result if isinstance(g, dict)]}


def _get_templates(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("template.get", {"output": ["templateid", "host", "name"]})
    if not isinstance(result, list):
        return {"templates": []}
    return {"templates": [t for t in result if isinstance(t, dict)]}


def _get_items(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["itemid", "name", "key_", "type", "value_type", "units", "lastvalue", "lastclock"],
        "sortfield": "name", "limit": 100,
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("item.get", params)
    if not isinstance(result, list):
        return {"items": [], "total_items": 0}
    items = []
    for item in result:
        if not isinstance(item, dict):
            continue
        items.append({
            "itemid": item.get("itemid"), "name": item.get("name"), "key_": item.get("key_"),
            "lastvalue": item.get("lastvalue"), "units": item.get("units"),
        })
    return {"items": items, "total_items": len(items)}


def _get_triggers(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["triggerid", "description", "expression", "priority", "status", "value"],
        "selectHosts": ["hostid", "host"],
        "filter": {"value": 1},
        "sortfield": "priority", "sortorder": "DESC",
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("trigger.get", params)
    if not isinstance(result, list):
        return {"triggers": [], "total_triggers": 0}
    triggers = []
    for t in result:
        if not isinstance(t, dict):
            continue
        pri = str(t.get("priority", "0"))
        triggers.append({
            "triggerid": t.get("triggerid"), "description": t.get("description"),
            "expression": t.get("expression"), "priority": t.get("priority"),
            "severity": _severity_label(pri), "status": t.get("status"),
            "value": t.get("value"), "hosts": t.get("hosts"),
        })
    severity_summary = _count_by_severity(triggers)
    return {"triggers": triggers, "total_triggers": len(triggers), "severity_summary": severity_summary}


def _get_events(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["eventid", "source", "object", "objectid", "clock", "value", "name", "severity"],
        "sortfield": "eventid", "sortorder": "DESC", "limit": 50,
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("event.get", params)
    if not isinstance(result, list):
        return {"events": [], "total_events": 0}
    events = []
    for e in result:
        if not isinstance(e, dict):
            continue
        events.append({
            "eventid": e.get("eventid"), "name": e.get("name"), "clock": e.get("clock"),
            "severity": e.get("severity"), "value": e.get("value"),
            "severity_label": _severity_label(e.get("severity", "0")),
        })
    return {"events": events, "total_events": len(events)}


def _get_problems(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["eventid", "objectid", "name", "clock", "severity"],
        "sortfield": "eventid", "sortorder": "DESC",
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("problem.get", params)
    if not isinstance(result, list):
        return {"problems": [], "total_problems": 0}
    problems = []
    for p in result:
        if not isinstance(p, dict):
            continue
        problems.append({
            "eventid": p.get("eventid"), "name": p.get("name"), "clock": p.get("clock"),
            "severity": p.get("severity"), "severity_label": _severity_label(p.get("severity", "0")),
        })
    severity_summary = _count_by_severity(problems)
    return {"problems": problems, "total_problems": len(problems), "severity_summary": severity_summary}


def _search_hosts(zapi: _ZabbixAPI, query: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["hostid", "host", "name", "status"],
        "search": {"name": query, "host": query},
        "searchWildcardsEnabled": True,
    }
    result = zapi.call("host.get", params)
    if not isinstance(result, list):
        return {"hosts": []}
    return {"hosts": [{"hostid": h.get("hostid"), "host": h.get("host"), "name": h.get("name"), "status": h.get("status")}
                      for h in result if isinstance(h, dict)]}


def _get_users(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("user.get", {"output": ["userid", "alias", "name", "surname", "roleid"]})
    if not isinstance(result, list):
        return {"users": []}
    return {"users": [u for u in result if isinstance(u, dict)]}


# ============================================================
# NEW CAPABILITIES
# ============================================================

def _get_problem_timeline(zapi: _ZabbixAPI, limit: int = 50) -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["eventid", "objectid", "name", "clock", "severity", "acknowledged"],
        "sortfield": "clock", "sortorder": "DESC",
        "limit": limit,
    }
    result = zapi.call("problem.get", params)
    if not isinstance(result, list):
        return {"problems": [], "total": 0}
    problems = []
    for p in result:
        if not isinstance(p, dict):
            continue
        problems.append({
            "eventid": p.get("eventid"), "name": p.get("name"), "clock": p.get("clock"),
            "severity": p.get("severity"), "severity_label": _severity_label(p.get("severity", "0")),
            "acknowledged": p.get("acknowledged", "0"),
        })
    return {"problems": problems, "total": len(problems)}


def _get_host_inventory(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("host.get", {
        "output": ["hostid", "host", "name", "status"],
        "selectGroups": ["groupid", "name"],
        "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
        "selectInventory": ["os", "type", "location"],
    })
    if not isinstance(result, list):
        return {"hosts": []}
    hosts = []
    for h in result:
        if not isinstance(h, dict):
            continue
        inventory = h.get("inventory")
        hosts.append({
            "hostid": h.get("hostid"), "host": h.get("host"), "name": h.get("name"),
            "status": h.get("status"), "os": inventory.get("os") if isinstance(inventory, dict) else None,
            "type": inventory.get("type") if isinstance(inventory, dict) else None,
        })
    return {"hosts": hosts, "total_hosts": len(hosts)}


def _get_host_interfaces(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    result = zapi.call("hostinterface.get", {
        "output": ["interfaceid", "ip", "dns", "port", "type", "main", "useip"],
        "hostids": hostid,
    }) if hostid else zapi.call("hostinterface.get", {"output": ["interfaceid", "ip", "dns", "port", "type", "main", "useip"]})
    if not isinstance(result, list):
        return {"interfaces": []}
    return {"interfaces": [i for i in result if isinstance(i, dict)], "total_interfaces": len(result) if isinstance(result, list) else 0}


def _get_maintenance_status(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("maintenance.get", {
        "output": ["maintenanceid", "name", "active_since", "active_till", "description"],
        "selectHosts": ["hostid", "host"],
    })
    if not isinstance(result, list):
        return {"maintenances": []}
    return {"maintenances": [m for m in result if isinstance(m, dict)], "total_maintenances": len(result)}


def _get_event_summary(zapi: _ZabbixAPI, limit: int = 100) -> dict[str, object]:
    result = zapi.call("event.get", {
        "output": ["eventid", "source", "object", "objectid", "clock", "value", "name", "severity"],
        "sortfield": "eventid", "sortorder": "DESC", "limit": limit,
    })
    if not isinstance(result, list):
        return {"events": [], "total": 0}
    events = []
    for e in result:
        if not isinstance(e, dict):
            continue
        events.append({
            "eventid": e.get("eventid"), "name": e.get("name"), "clock": e.get("clock"),
            "severity": e.get("severity"), "severity_label": _severity_label(e.get("severity", "0")),
            "value": e.get("value"),
        })
    severity_summary = _count_by_severity(events)
    return {"events": events, "total": len(events), "severity_summary": severity_summary}


# ============================================================
# CAPABILITIES REGISTRY
# ============================================================

_CAPABILITIES: dict[str, Callable[..., dict[str, object]]] = {
    "get_api_version": _get_api_version,
    "get_hosts": _get_hosts,
    "get_host": _get_host,
    "search_hosts": _search_hosts,
    "get_host_groups": _get_host_groups,
    "get_templates": _get_templates,
    "get_items": _get_items,
    "get_triggers": _get_triggers,
    "get_events": _get_events,
    "get_problems": _get_problems,
    "get_problem_timeline": _get_problem_timeline,
    "get_host_inventory": _get_host_inventory,
    "get_host_interfaces": _get_host_interfaces,
    "get_maintenance_status": _get_maintenance_status,
    "get_event_summary": _get_event_summary,
    "get_users": _get_users,
}


class ZabbixTool(Tool):
    def __init__(self, url: str = "http://localhost/zabbix", token: str = "", timeout: int = 10) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        action = arguments.get("action")
        if not isinstance(action, str):
            return ToolResult(success=False, error="Missing action.")

        handler = _CAPABILITIES.get(action)
        if handler is None:
            available = ", ".join(sorted(_CAPABILITIES))
            return ToolResult(success=False, error=f"Unknown action: '{action}'. Available actions: {available}.")

        api = _ZabbixAPI(url=self._url, token=self._token, timeout=self._timeout)
        extra = {k: v for k, v in arguments.items() if k != "action"}

        try:
            data = handler(api, **extra)
        except RuntimeError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"ZabbixTool error: {exc}")

        return ToolResult(success=True, data=data)
