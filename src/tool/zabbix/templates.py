from __future__ import annotations

from .client import _ZabbixAPI

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


def _get_templates(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "template.get",
        {
            "output": ["templateid", "host", "name", "description"],
            "selectGroups": ["groupid", "name"],
        },
    )
    if not isinstance(result, list):
        return {"templates": [], "total": 0}
    templates = []
    for template in result:
        if not isinstance(template, dict):
            continue
        name = template.get("name", template.get("host", ""))
        templates.append(
            {
                "templateid": template.get("templateid"),
                "name": name,
                "host": template.get("host", ""),
                "description": template.get("description", ""),
                "domain": _classify_template_domain(name),
            }
        )
    domain_summary: dict[str, int] = {}
    for template in templates:
        domain = template["domain"]
        domain_summary[domain] = domain_summary.get(domain, 0) + 1
    return {
        "templates": templates,
        "total": len(templates),
        "domain_summary": domain_summary,
    }
