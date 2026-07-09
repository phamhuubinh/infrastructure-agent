from __future__ import annotations

import json
from collections.abc import Callable
from urllib import error as urlerror
from urllib import request

from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool


class _ZabbixAPI:
    """
    Minimal Zabbix API client using token-based authentication.

    The token is sent in every request via the "auth" field.
    No session state is cached between calls.
    """

    def __init__(
        self,
        url: str,
        token: str,
        timeout: int = 10,
    ) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._request_id = 0

    def call(
        self,
        method: str,
        params: dict[str, object] | None = None,
    ) -> object:
        self._request_id += 1
        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "auth": self._token,
            "id": self._request_id,
        }

        headers = {"Content-Type": "application/json-rpc"}
        body = json.dumps(payload).encode("utf-8")

        try:
            req = request.Request(
                url=f"{self._url}/api_jsonrpc.php",
                data=body,
                headers=headers,
                method="POST",
            )
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


def _get_api_version(zapi: _ZabbixAPI) -> dict[str, object]:
    return {"version": zapi.call("apiinfo.version")}


def _get_hosts(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "host.get",
        {
            "output": ["hostid", "host", "name", "status"],
            "selectGroups": ["groupid", "name"],
            "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
        },
    )
    if not isinstance(result, list):
        return {"hosts": []}
    hosts = []
    for h in result:
        if not isinstance(h, dict):
            continue
        hosts.append({
            "hostid": h.get("hostid"),
            "host": h.get("host"),
            "name": h.get("name"),
            "status": h.get("status"),
            "groups": h.get("groups"),
            "interfaces": h.get("interfaces"),
        })
    return {"hosts": hosts}


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
    hosts = []
    for h in result:
        if not isinstance(h, dict):
            continue
        hosts.append({
            "hostid": h.get("hostid"),
            "host": h.get("host"),
            "name": h.get("name"),
            "status": h.get("status"),
            "groups": h.get("groups"),
            "interfaces": h.get("interfaces"),
        })
    return {"hosts": hosts}


def _get_host_groups(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "hostgroup.get",
        {"output": ["groupid", "name"]},
    )
    if not isinstance(result, list):
        return {"groups": []}
    return {"groups": [g for g in result if isinstance(g, dict)]}


def _get_templates(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "template.get",
        {"output": ["templateid", "host", "name"]},
    )
    if not isinstance(result, list):
        return {"templates": []}
    return {"templates": [t for t in result if isinstance(t, dict)]}


def _get_items(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["itemid", "name", "key_", "type", "value_type", "units", "lastvalue", "lastclock"],
        "sortfield": "name",
        "limit": 100,
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("item.get", params)
    if not isinstance(result, list):
        return {"items": []}
    items = []
    for item in result:
        if not isinstance(item, dict):
            continue
        items.append({
            "itemid": item.get("itemid"),
            "name": item.get("name"),
            "key_": item.get("key_"),
            "lastvalue": item.get("lastvalue"),
            "units": item.get("units"),
        })
    return {"items": items}


def _get_triggers(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["triggerid", "description", "expression", "priority", "status", "value"],
        "selectHosts": ["hostid", "host"],
        "filter": {"value": 1},
        "sortfield": "priority",
        "sortorder": "DESC",
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("trigger.get", params)
    if not isinstance(result, list):
        return {"triggers": []}
    triggers = []
    for t in result:
        if not isinstance(t, dict):
            continue
        triggers.append({
            "triggerid": t.get("triggerid"),
            "description": t.get("description"),
            "priority": t.get("priority"),
            "status": t.get("status"),
            "value": t.get("value"),
            "hosts": t.get("hosts"),
        })
    return {"triggers": triggers}


def _get_events(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["eventid", "source", "object", "objectid", "clock", "value", "name", "severity"],
        "sortfield": "clock",
        "sortorder": "DESC",
        "limit": 50,
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("event.get", params)
    if not isinstance(result, list):
        return {"events": []}
    events = []
    for e in result:
        if not isinstance(e, dict):
            continue
        events.append({
            "eventid": e.get("eventid"),
            "name": e.get("name"),
            "clock": e.get("clock"),
            "severity": e.get("severity"),
            "value": e.get("value"),
        })
    return {"events": events}


def _get_problems(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["eventid", "objectid", "name", "clock", "severity"],
        "sortfield": "clock",
        "sortorder": "DESC",
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("problem.get", params)
    if not isinstance(result, list):
        return {"problems": []}
    problems = []
    for p in result:
        if not isinstance(p, dict):
            continue
        problems.append({
            "eventid": p.get("eventid"),
            "name": p.get("name"),
            "clock": p.get("clock"),
            "severity": p.get("severity"),
        })
    return {"problems": problems}


def _search_hosts(zapi: _ZabbixAPI, query: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["hostid", "host", "name", "status"],
        "search": {"name": query, "host": query},
        "searchWildcardsEnabled": True,
    }
    result = zapi.call("host.get", params)
    if not isinstance(result, list):
        return {"hosts": []}
    hosts = []
    for h in result:
        if not isinstance(h, dict):
            continue
        hosts.append({
            "hostid": h.get("hostid"),
            "host": h.get("host"),
            "name": h.get("name"),
            "status": h.get("status"),
        })
    return {"hosts": hosts}


def _get_users(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "user.get",
        {"output": ["userid", "alias", "name", "surname", "roleid", "autologin", "autologout"]},
    )
    if not isinstance(result, list):
        return {"users": []}
    return {"users": [u for u in result if isinstance(u, dict)]}


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
    "get_users": _get_users,
}


class ZabbixTool(Tool):
    """
    Tool con của KnowledgeTool, chịu trách nhiệm cho domain Zabbix.

    KnowledgeTool gọi execute() với một capability đã đặt tên (vd.
    "get_hosts"); ZabbixTool không biết Agent, không biết Model, và
    không route sang Tool con khác.

    Nếu capability không tồn tại, execute() trả về ToolResult thất bại
    kèm danh sách capability hợp lệ.

    Để thêm capability: viết một hàm trả về structured data, sau đó
    thêm một entry vào _CAPABILITIES. Không cần sửa gì khác.
    """

    def __init__(
        self,
        url: str = "http://localhost/zabbix",
        token: str = "",
        timeout: int = 10,
    ) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        action = arguments.get("action")

        if not isinstance(action, str):
            return ToolResult(
                success=False,
                error="Missing action.",
            )

        handler = _CAPABILITIES.get(action)

        if handler is None:
            available = ", ".join(sorted(_CAPABILITIES))

            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'. Available actions: {available}.",
            )

        api = _ZabbixAPI(
            url=self._url,
            token=self._token,
            timeout=self._timeout,
        )

        extra = {k: v for k, v in arguments.items() if k != "action"}

        try:
            data = handler(api, **extra)
        except RuntimeError as exc:
            return ToolResult(
                success=False,
                error=str(exc),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"ZabbixTool error: {exc}",
            )

        return ToolResult(
            success=True,
            data=data,
        )
