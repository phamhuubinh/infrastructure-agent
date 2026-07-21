from __future__ import annotations

from .client import _ZabbixAPI


def _format_host(host: dict[str, object]) -> dict[str, object]:
    groups = host.get("groups")
    interfaces = host.get("interfaces")
    tags = host.get("tags")
    return {
        "hostid": host.get("hostid"),
        "host": host.get("host"),
        "name": host.get("name"),
        "status": host.get("status"),
        "groups": ", ".join(g.get("name", "") for g in groups if isinstance(g, dict))
        if isinstance(groups, list)
        else "",
        "ip": ", ".join(i.get("ip", "") for i in interfaces if isinstance(i, dict))
        if isinstance(interfaces, list)
        else "",
        "proxy_hostid": host.get("proxy_hostid"),
        "available": host.get("available"),
        "error": host.get("error", ""),
        "maintenance_status": host.get("maintenance_status"),
        "monitored_by": host.get("monitored_by"),
        "tags": [
            {"tag": tag.get("tag", ""), "value": tag.get("value", "")}
            for tag in tags
            if isinstance(tag, dict)
        ]
        if isinstance(tags, list)
        else [],
    }


def _host_params() -> dict[str, object]:
    return {
        "output": [
            "hostid",
            "host",
            "name",
            "status",
            "proxy_hostid",
            "available",
            "error",
            "maintenance_status",
            "monitored_by",
        ],
        "selectGroups": ["groupid", "name"],
        "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
        "selectTags": ["tag", "value"],
    }


def _get_hosts(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("host.get", _host_params())
    if not isinstance(result, list):
        return {"hosts": [], "total_hosts": 0}
    hosts = [_format_host(host) for host in result if isinstance(host, dict)]
    enabled = sum(host.get("status") == "0" for host in hosts)
    return {
        "hosts": hosts,
        "total_hosts": len(hosts),
        "enabled_hosts": enabled,
        "disabled_hosts": len(hosts) - enabled,
    }


def _get_host(zapi: _ZabbixAPI, host: str = "") -> dict[str, object]:
    params = _host_params()
    if host:
        params["hostids" if host.isdigit() else "filter"] = (
            host if host.isdigit() else {"host": host}
        )
    result = zapi.call("host.get", params)
    return (
        {"hosts": [_format_host(item) for item in result if isinstance(item, dict)]}
        if isinstance(result, list)
        else {"hosts": []}
    )


def _search_hosts(zapi: _ZabbixAPI, query: str = "") -> dict[str, object]:
    result = zapi.call(
        "host.get",
        {
            "output": ["hostid", "host", "name", "status"],
            "search": {"name": query, "host": query},
            "searchWildcardsEnabled": True,
        },
    )
    if not isinstance(result, list):
        return {"hosts": []}
    return {
        "hosts": [
            {key: host.get(key) for key in ("hostid", "host", "name", "status")}
            for host in result
            if isinstance(host, dict)
        ]
    }


def _get_host_groups(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call("hostgroup.get", {"output": ["groupid", "name"]})
    return (
        {"groups": [group for group in result if isinstance(group, dict)]}
        if isinstance(result, list)
        else {"groups": []}
    )


def _get_host_inventory(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "host.get",
        {
            "output": ["hostid", "host", "name", "status"],
            "selectGroups": ["groupid", "name"],
            "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type"],
            "selectInventory": ["os", "type", "location", "hardware", "software"],
        },
    )
    if not isinstance(result, list):
        return {"hosts": []}
    hosts = []
    for host in result:
        if not isinstance(host, dict):
            continue
        inventory = host.get("inventory")
        hosts.append(
            {
                "hostid": host.get("hostid"),
                "host": host.get("host"),
                "name": host.get("name"),
                "status": host.get("status"),
                **{
                    key: inventory.get(key) if isinstance(inventory, dict) else None
                    for key in ("os", "type", "location", "hardware")
                },
            }
        )
    return {"hosts": hosts, "total_hosts": len(hosts)}


def _get_host_interfaces(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["interfaceid", "ip", "dns", "port", "type", "main", "useip"]
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("hostinterface.get", params)
    if not isinstance(result, list):
        return {"interfaces": []}
    return {
        "interfaces": [item for item in result if isinstance(item, dict)],
        "total_interfaces": len(result),
    }
