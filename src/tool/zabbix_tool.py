from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from urllib import error as urlerror
from urllib import request

from src.shared.capability import Capability
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
# ITEM KEY -> OBSERVED SIGNAL MAPPING (deterministic)
# ============================================================

_ITEM_SIGNAL_MAP: dict[str, str] = {
    "system.cpu.util": "CPU Utilization",
    "system.cpu.num": "CPU Count",
    "system.cpu.load": "CPU Load",
    "vm.memory.size": "Memory Utilization",
    "vfs.fs.size": "Disk Capacity",
    "vfs.fs.discovery": "Filesystem Discovery",
    "vfs.fs.inode": "Inode Usage",
    "net.if.in": "Network Throughput",
    "net.if.out": "Network Throughput",
    "net.if.total": "Network Throughput",
    "icmpping": "Availability",
    "icmppingloss": "Packet Loss",
    "icmppingsec": "Latency",
    "system.uptime": "System Uptime",
    "agent.ping": "Agent Availability",
    "proc.num": "Process Count",
    "service.info": "Service Status",
    "system.hostname": "System Identity",
    "system.uname": "System Identity",
    "system.sw.os": "System Identity",
    "system.swap.size": "Swap Utilization",
    "vfs.dev.read": "Disk IOPS",
    "vfs.dev.write": "Disk IOPS",
    "vfs.dev.read.ops": "Disk IOPS",
    "vfs.dev.write.ops": "Disk IOPS",
    "vfs.dev.read.latency": "Disk Latency",
    "vfs.dev.write.latency": "Disk Latency",
    "system.localtime": "System Time",
    "system.boottime": "Boot Time",
    "sensor.temp": "Temperature",
    "sensor.fan": "Fan",
    "sensor.psu": "Power Supply",
    "sensor.voltage": "Voltage",
    "kernel.maxprocs": "Kernel Limits",
    "kernel.openfiles": "Kernel Limits",
    "zabbix.host.count": "Zabbix Statistics",
    "zabbix.item.count": "Zabbix Statistics",
    "zabbix.trigger.count": "Zabbix Statistics",
}


def _classify_item_key(key: str) -> str:
    key_lower = key.lower().strip()
    exact = _ITEM_SIGNAL_MAP.get(key_lower)
    if exact:
        return exact
    if "docker." in key_lower:
        return "Container"
    if "vmware." in key_lower:
        return "Virtualization"
    if "snmp." in key_lower or key_lower.startswith("snmp_"):
        return "SNMP Monitoring"
    if "ipmi." in key_lower:
        return "IPMI Hardware"
    if "zabbix" in key_lower:
        return "Zabbix Statistics"
    if "jmx" in key_lower:
        return "JMX Monitoring"
    if "grinder" in key_lower:
        return "Application Performance"
    if "log" in key_lower and "count" in key_lower:
        return "Log Monitoring"
    if "log" in key_lower and ("match" in key_lower or "event" in key_lower):
        return "Log Event"
    if "trap" in key_lower:
        return "SNMP Trap"
    if key_lower.startswith("eventlog"):
        return "Windows Event Log"
    if "perf_counter" in key_lower or "perfcount" in key_lower:
        return "Windows Performance"
    if "service_state" in key_lower or "service.info" in key_lower:
        return "Service Status"
    if "web.page" in key_lower or "web.test" in key_lower:
        return "Web Monitoring"
    if "ssh" in key_lower and "run" in key_lower:
        return "Remote Command"
    if "telnet" in key_lower:
        return "Remote Command"
    if key_lower.startswith("db.") or key_lower.startswith("database."):
        return "Database"
    if "pgsql" in key_lower or "mysql" in key_lower or "oracle" in key_lower or "mssql" in key_lower:
        return "Database"
    if "redis" in key_lower:
        return "Cache"
    if "memcached" in key_lower:
        return "Cache"
    if "rabbitmq" in key_lower or "kafka" in key_lower:
        return "Message Queue"
    if "nginx" in key_lower or "apache" in key_lower or "httpd" in key_lower:
        return "Web Server"
    if "postfix" in key_lower or "sendmail" in key_lower:
        return "Mail Server"
    if "cert" in key_lower:
        return "TLS Certificate"
    if "ssl" in key_lower:
        return "TLS Certificate"
    if "dns" in key_lower:
        return "DNS"
    if "dhcp" in key_lower:
        return "DHCP"
    if "bgp" in key_lower:
        return "BGP"
    if "ospf" in key_lower:
        return "OSPF"
    if "vpn" in key_lower:
        return "VPN"
    if "firewall" in key_lower:
        return "Firewall"
    if "nat" in key_lower:
        return "NAT"
    if "backup" in key_lower:
        return "Backup"
    if "replication" in key_lower or "replica" in key_lower:
        return "Replication"
    if "raid" in key_lower:
        return "RAID"
    if "ups" in key_lower:
        return "UPS"
    return "Other"


# ============================================================
# TEMPLATE DOMAIN CLASSIFICATION
# ============================================================

_TEMPLATE_DOMAIN_MAP: dict[str, str] = {
    "linux": "Compute",
    "windows": "Compute",
    "cisco": "Networking",
    "juniper": "Networking",
    "arista": "Networking",
    "huawei": "Networking",
    "mikrotik": "Networking",
    "router": "Routing",
    "switch": "Switching",
    "firewall": "Security",
    "fortigate": "Security",
    "paloalto": "Security",
    "checkpoint": "Security",
    "vmware": "Virtualization",
    "vsphere": "Virtualization",
    "hyper-v": "Virtualization",
    "docker": "Container Platform",
    "kubernetes": "Container Platform",
    "mysql": "Database",
    "postgresql": "Database",
    "oracle": "Database",
    "mssql": "Database",
    "mongodb": "Database",
    "redis": "Cache",
    "apache": "Web Server",
    "nginx": "Web Server",
    "iis": "Web Server",
    "tomcat": "Application Server",
    "zabbix": "Monitoring",
    "snmptrap": "Monitoring",
    "dns": "DNS",
    "bind": "DNS",
    "dhcp": "DHCP",
    "ldap": "Identity",
    "openldap": "Identity",
    "ad": "Identity",
    "backup": "Backup",
    "bacula": "Backup",
    "veeam": "Backup",
}


def _classify_template_domain(template_name: str) -> str:
    name_lower = template_name.lower()
    for keyword, domain in _TEMPLATE_DOMAIN_MAP.items():
        if keyword in name_lower:
            return domain
    return "Other"


# ============================================================
# ITEM FORMAT WITH NORMALIZED EVIDENCE
# ============================================================

def _format_item(item: dict[str, object]) -> dict[str, object]:
    key = str(item.get("key_", ""))
    return {
        "itemid": item.get("itemid"),
        "name": item.get("name", ""),
        "key_": key,
        "lastvalue": item.get("lastvalue"),
        "units": item.get("units"),
        "value_type": item.get("value_type", "0"),
        "observed_signal": _classify_item_key(key),
        "infrastructure_domain": "Monitoring",
    }


# ============================================================
# CAPABILITY HANDLERS
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
    tags = h.get("tags")
    return {
        "hostid": h.get("hostid"), "host": h.get("host"), "name": h.get("name"),
        "status": h.get("status"), "groups": group_names, "ip": ips,
        "proxy_hostid": h.get("proxy_hostid"),
        "available": h.get("available"),
        "error": h.get("error", ""),
        "maintenance_status": h.get("maintenance_status"),
        "monitored_by": h.get("monitored_by"),
        "tags": [{"tag": t.get("tag", ""), "value": t.get("value", "")}
                 for t in tags if isinstance(t, dict)] if isinstance(tags, list) else [],
    }


def _get_hosts(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("host.get", {
        "output": ["hostid", "host", "name", "status", "proxy_hostid", "available", "error",
                    "maintenance_status", "monitored_by"],
        "selectGroups": ["groupid", "name"],
        "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
        "selectTags": ["tag", "value"],
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
        "output": ["hostid", "host", "name", "status", "proxy_hostid", "available", "error",
                    "maintenance_status", "monitored_by"],
        "selectGroups": ["groupid", "name"],
        "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
        "selectTags": ["tag", "value"],
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
    result = zapi.call("template.get", {"output": ["templateid", "host", "name", "description"],
                                         "selectGroups": ["groupid", "name"]})
    if not isinstance(result, list):
        return {"templates": [], "total": 0}
    templates = []
    for t in result:
        if not isinstance(t, dict):
            continue
        name = t.get("name", t.get("host", ""))
        templates.append({
            "templateid": t.get("templateid"), "name": name, "host": t.get("host", ""),
            "description": t.get("description", ""),
            "domain": _classify_template_domain(name),
        })
    by_domain: dict[str, int] = {}
    for t in templates:
        d = t["domain"]
        by_domain[d] = by_domain.get(d, 0) + 1
    return {"templates": templates, "total": len(templates), "domain_summary": by_domain}


def _get_items(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["itemid", "name", "key_", "type", "value_type", "units", "lastvalue", "lastclock", "error", "status"],
        "sortfield": "name", "limit": 500,
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("item.get", params)
    if not isinstance(result, list):
        return {"items": [], "total_items": 0}
    items = [_format_item(item) for item in result if isinstance(item, dict)]
    by_signal: dict[str, int] = {}
    for item in items:
        sig = item.get("observed_signal", "Other")
        by_signal[sig] = by_signal.get(sig, 0) + 1
    return {"items": items, "total_items": len(items), "observed_signal_summary": by_signal}


def _get_triggers(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["triggerid", "description", "expression", "priority", "status", "value",
                    "lastchange", "comments", "url", "error"],
        "selectHosts": ["hostid", "host"],
        "selectTags": ["tag", "value"],
        "selectDependencies": ["triggerid", "description"],
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
        deps = t.get("dependencies", [])
        tags = t.get("tags", [])
        triggers.append({
            "triggerid": t.get("triggerid"), "description": t.get("description"),
            "expression": t.get("expression"), "priority": t.get("priority"),
            "severity": _severity_label(pri), "status": t.get("status"),
            "value": t.get("value"), "hosts": t.get("hosts"),
            "lastchange": t.get("lastchange"),
            "comments": t.get("comments", ""),
            "url": t.get("url", ""),
            "error": t.get("error", ""),
            "dependencies": [{"triggerid": d.get("triggerid"), "description": d.get("description", "")}
                             for d in deps if isinstance(d, dict)] if isinstance(deps, list) else [],
            "tags": [{"tag": tg.get("tag", ""), "value": tg.get("value", "")}
                     for tg in tags if isinstance(tg, dict)] if isinstance(tags, list) else [],
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
        "selectInventory": ["os", "type", "location", "hardware", "software"],
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
            "status": h.get("status"),
            "os": inventory.get("os") if isinstance(inventory, dict) else None,
            "type": inventory.get("type") if isinstance(inventory, dict) else None,
            "location": inventory.get("location") if isinstance(inventory, dict) else None,
            "hardware": inventory.get("hardware") if isinstance(inventory, dict) else None,
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

_CAPABILITIES: dict[str, Capability] = {
    "get_api_version": Capability("get_api_version", _get_api_version, "monitoring", ("monitor", "inventory"), ("get_hosts",), ("monitoring-version",)),
    "get_hosts": Capability("get_hosts", _get_hosts, "monitoring", ("monitor", "inventory"), ("get_problems", "get_triggers"), ("zabbix-hosts",)),
    "get_host": Capability("get_host", _get_host, "monitoring", ("monitor", "inventory"), ("get_items",), ("zabbix-hosts",)),
    "search_hosts": Capability("search_hosts", _search_hosts, "monitoring", ("monitor", "inventory", "discovery"), ("get_host",), ("zabbix-hosts",)),
    "get_host_groups": Capability("get_host_groups", _get_host_groups, "monitoring", ("monitor", "inventory"), ("get_hosts",), ("zabbix-groups",)),
    "get_templates": Capability("get_templates", _get_templates, "monitoring", ("monitor", "inventory", "configuration"), ("get_hosts",), ("zabbix-templates",)),
    "get_items": Capability("get_items", _get_items, "monitoring", ("monitor", "inventory", "investigation"), ("get_triggers",), ("zabbix-items",)),
    "get_triggers": Capability("get_triggers", _get_triggers, "monitoring", ("monitor", "alerts"), ("get_problems", "get_events"), ("zabbix-triggers", "alert_severity")),
    "get_events": Capability("get_events", _get_events, "monitoring", ("monitor", "events", "timeline"), ("get_problems",), ("zabbix-events",)),
    "get_problems": Capability("get_problems", _get_problems, "monitoring", ("monitor", "alerts", "incidents"), ("get_triggers", "get_events"), ("zabbix-problems",)),
    "get_problem_timeline": Capability("get_problem_timeline", _get_problem_timeline, "monitoring", ("monitor", "events", "timeline"), ("get_problems",), ("zabbix-events",)),
    "get_host_inventory": Capability("get_host_inventory", _get_host_inventory, "monitoring", ("monitor", "inventory"), ("get_hosts",), ("zabbix-hosts",)),
    "get_host_interfaces": Capability("get_host_interfaces", _get_host_interfaces, "monitoring", ("monitor", "inventory"), ("get_hosts",), ("zabbix-interfaces",)),
    "get_maintenance_status": Capability("get_maintenance_status", _get_maintenance_status, "monitoring", ("monitor", "maintenance"), ("get_hosts",), ("zabbix-maintenance",)),
    "get_event_summary": Capability("get_event_summary", _get_event_summary, "monitoring", ("monitor", "events", "timeline"), ("get_problems",), ("zabbix-events",)),
    "get_users": Capability("get_users", _get_users, "monitoring", ("monitor", "inventory"), (), ("zabbix-users",)),
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

        cap = _CAPABILITIES.get(action)
        if cap is None:
            available = ", ".join(sorted(_CAPABILITIES))
            return ToolResult(success=False, error=f"Unknown action: '{action}'. Available actions: {available}.")

        handler = cap.handler if isinstance(cap, Capability) else cap

        api = _ZabbixAPI(url=self._url, token=self._token, timeout=self._timeout)
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
            return ToolResult(success=False, error=f"ZabbixTool error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, error=f"ZabbixTool error: {exc}")

        return ToolResult(success=True, data=data)
