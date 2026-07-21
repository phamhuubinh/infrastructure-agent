from __future__ import annotations

from .client import _ZabbixAPI

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
    if exact := _ITEM_SIGNAL_MAP.get(key_lower):
        return exact
    for match, label in (
        ("docker.", "Container"),
        ("vmware.", "Virtualization"),
        ("ipmi.", "IPMI Hardware"),
        ("zabbix", "Zabbix Statistics"),
        ("jmx", "JMX Monitoring"),
        ("trap", "SNMP Trap"),
        ("telnet", "Remote Command"),
        ("redis", "Cache"),
        ("memcached", "Cache"),
        ("rabbitmq", "Message Queue"),
        ("kafka", "Message Queue"),
        ("cert", "TLS Certificate"),
        ("ssl", "TLS Certificate"),
        ("dns", "DNS"),
        ("dhcp", "DHCP"),
        ("bgp", "BGP"),
        ("ospf", "OSPF"),
        ("vpn", "VPN"),
        ("firewall", "Firewall"),
        ("nat", "NAT"),
        ("backup", "Backup"),
        ("raid", "RAID"),
        ("ups", "UPS"),
    ):
        if match in key_lower:
            return label
    if "snmp." in key_lower or key_lower.startswith("snmp_"):
        return "SNMP Monitoring"
    if "log" in key_lower and "count" in key_lower:
        return "Log Monitoring"
    if "log" in key_lower and ("match" in key_lower or "event" in key_lower):
        return "Log Event"
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
    if key_lower.startswith(("db.", "database.")) or any(
        db in key_lower for db in ("pgsql", "mysql", "oracle", "mssql")
    ):
        return "Database"
    if any(web in key_lower for web in ("nginx", "apache", "httpd")):
        return "Web Server"
    if "postfix" in key_lower or "sendmail" in key_lower:
        return "Mail Server"
    if "replication" in key_lower or "replica" in key_lower:
        return "Replication"
    if "grinder" in key_lower:
        return "Application Performance"
    return "Other"


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


def _get_api_version(zapi: _ZabbixAPI) -> dict[str, object]:
    return {"version": zapi.call("apiinfo.version", skip_auth=True)}


def _get_items(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": [
            "itemid",
            "name",
            "key_",
            "type",
            "value_type",
            "units",
            "lastvalue",
            "lastclock",
            "error",
            "status",
        ],
        "sortfield": "name",
        "limit": 500,
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("item.get", params)
    if not isinstance(result, list):
        return {"items": [], "total_items": 0}
    items = [_format_item(item) for item in result if isinstance(item, dict)]
    signal_summary: dict[str, int] = {}
    for item in items:
        signal = item.get("observed_signal", "Other")
        signal_summary[signal] = signal_summary.get(signal, 0) + 1
    return {
        "items": items,
        "total_items": len(items),
        "observed_signal_summary": signal_summary,
    }
