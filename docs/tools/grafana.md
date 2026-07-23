# Grafana Tool

> Grafana observability platform integration for dashboard, datasource, alert, and annotation data retrieval.

## Overview

The Grafana Tool queries a Grafana instance via its HTTP API to collect observability evidence. It is dispatched by the KnowledgeTool when infrastructure queries require dashboard metrics or alert state.

## Capabilities

| Capability | Description |
|------------|-------------|
| `dashboards` | List dashboards with panel metadata, metrics, and transformations |
| `datasources` | List configured datasources with type and domain classification |
| `alerts` | Fetch alert rules, current state, and firing alerts |
| `annotations` | Retrieve annotation events (deployments, incidents, changes) |
| `health` | Grafana instance health check |
| `version` | Grafana server version and admin statistics |

## Usage Examples

### Via CLI

```bash
orion run
> Show all dashboards from grafana
```

### Via API

```bash
curl -X POST http://localhost:61888/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Are there any firing alerts in Grafana?"}'
```

Expected response:

```json
{
  "response": "...",
  "steps": [
    {
      "stage": "evidence",
      "items": [
        {
          "evidence_name": "grafana_alerts",
          "success": true,
          "data": {
            "alert_rules": [
              {
                "title": "High CPU Usage",
                "state": "firing",
                "severity": "critical"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### Python

```python
from src.tool.grafana import GrafanaTool
from src.tool.grafana.provider import GrafanaProvider

provider = GrafanaProvider(
    base_url="https://grafana.example.com",
    api_token="glsa_...",
)
tool = GrafanaTool(provider=provider)
result = tool.execute({"capability": "dashboards"})
print(result.data)
```

## Configuration

Secrets are stored in `config/secrets.local.json`:

```json
{
  "grafana": {
    "base_url": "https://grafana.example.com",
    "api_token": "glsa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

## Notes

- The Grafana Tool requires a Grafana API token (Service Account or API Key) with appropriate permissions.
- Dashboard panel extraction parses Prometheus/Loki queries and classifies data sources by infrastructure domain.
- Annotations are limited to the most recent 50 by default.