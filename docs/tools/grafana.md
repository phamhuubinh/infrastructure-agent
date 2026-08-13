# Grafana Tool

> Grafana observability platform integration for dashboard, datasource, alert, and annotation data retrieval.

## Overview

The Grafana Tool queries a Grafana instance via its HTTP API to collect observability evidence. It is dispatched by the KnowledgeTool when infrastructure queries require dashboard metrics or alert state.

## Capabilities

| Capability | Description |
|------------|-------------|
| `dashboards` | List dashboards |
| `dashboard_search` | Search dashboards |
| `dashboard_summary` | Summarize dashboard inventory |
| `dashboard_details` | Read panels and queries for one dashboard |
| `folders` | List dashboard folders |
| `datasources` | List configured datasources with type and domain classification |
| `alert_rules` | Fetch alert rules and state |
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
  "assessment": "...",
  "steps": [
    {
      "stage": "evidence",
      "items": [
        {
          "evidence_name": "grafana_alerts",
          "success": true
        }
      ]
    }
  ]
}
```

### Python

```python
from src.tool.grafana import GrafanaTool

tool = GrafanaTool(
    url="https://grafana.example.com",
    token="glsa_...",
)
result = tool.execute({"action": "dashboards"})
print(result.data)
```

## Configuration

Secrets are stored outside the project in `/etc/orion/tool-credentials.json`:

```json
{
  "grafana": {
    "url": "https://grafana.example.com",
    "token": "glsa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

Docker Compose mounts this ignored file read-only into the API container. After changing it, run `docker compose up -d --force-recreate api` so Compose remounts the secret.

## Notes

- The Grafana Tool requires a Grafana API token (Service Account or API Key) with appropriate permissions.
- Dashboard panel extraction parses Prometheus/Loki queries and classifies data sources by infrastructure domain.
- Annotations are limited to the most recent 50 by default.
