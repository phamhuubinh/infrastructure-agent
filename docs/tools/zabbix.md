# Zabbix Tool

> Zabbix monitoring platform integration for hosts, triggers, events, and history retrieval.

## Overview

The Zabbix Tool queries a Zabbix server via its JSON-RPC API to collect monitoring evidence. It is dispatched by the KnowledgeTool when infrastructure queries require host status, trigger problems, event timelines, or monitoring history.

## Capabilities

| Area | Registered capabilities |
|---|---|
| API and hosts | `get_api_version`, `get_hosts`, `get_host`, `search_hosts`, `get_host_groups`, `get_host_inventory`, `get_host_interfaces` |
| Monitoring data | `get_items`, `get_triggers`, `get_problems` |
| Events | `get_events`, `get_problem_timeline`, `get_event_summary`, `get_maintenance_status` |
| Configuration | `get_templates`, `get_users` |

## Usage Examples

### Via CLI

```bash
orion run
> Show all Zabbix hosts with active problems
```

### Via API

```bash
curl -X POST http://localhost:61888/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Are there any active triggers on zabbix-server?"}'
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
          "evidence_name": "zabbix_triggers",
          "success": true
        }
      ]
    }
  ]
}
```

### Python

```python
from src.tool.zabbix import ZabbixTool
tool = ZabbixTool(
    url="https://zabbix.example.com/api_jsonrpc.php",
    token="your-zabbix-api-token",
)
result = tool.execute({"action": "get_hosts"})
print(result.data)
```

## Configuration

Secrets are stored outside the project in `/etc/orion/tool-credentials.json`:

```json
{
  "zabbix": {
    "url": "https://zabbix.example.com/zabbix",
    "token": "your-zabbix-api-token"
  }
}
```

Docker Compose mounts this ignored file read-only into the API container. After changing it, run `docker compose up -d --force-recreate api` so Compose remounts the secret.

## Notes

- Uses the Zabbix JSON-RPC API with token authentication.
- All responses are formatted into consistent dict structures with string-based severity labels.
- Host search supports fuzzy matching.
- Event timeline queries default to 50 results, configurable via limit parameter.
