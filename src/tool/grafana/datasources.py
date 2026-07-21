from __future__ import annotations

from .provider import GrafanaProvider

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


def datasource_domain(ds_type: str) -> str:
    return _INFRA_DOMAINS.get(ds_type.lower(), "Unknown")


def get_datasources(api: GrafanaProvider) -> dict[str, object]:
    result = api.get("/api/datasources")
    if not isinstance(result, list):
        return {"datasources": [], "total": 0}
    datasources = [
        {
            "name": item.get("name", ""),
            "type": item.get("type", ""),
            "url": item.get("url", ""),
            "is_default": item.get("isDefault", False),
            "uid": item.get("uid", ""),
            "database": item.get("database", ""),
            "user": item.get("user", ""),
            "access": item.get("access", ""),
            "basic_auth": item.get("basicAuth", False),
            "domain": datasource_domain(item.get("type", "")),
        }
        for item in result
        if isinstance(item, dict)
    ]
    return {"datasources": datasources, "total": len(datasources)}
