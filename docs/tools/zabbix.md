# Zabbix Tool

> Zabbix monitoring platform integration for hosts, triggers, events, and history retrieval.

## Overview

The Zabbix Tool queries a Zabbix server via its JSON-RPC API to collect monitoring evidence. It is dispatched by the KnowledgeTool when infrastructure queries require host status, trigger problems, event timelines, or monitoring history.

## Capabilities

| Capability | Description |
|------------|-------------|
| `hosts` | List hosts, search hosts, host groups, inventory, interfaces |
| `triggers` | Trigger state, problem listing, severity levels |
| `events` | Event history, problem timeline, maintenance status, event summary, user listing |
| `templates` | Template listing |
| `history` | Metric history retrieval, API version check, item listing |

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
  "response": "...",
  "steps": [
    {
      "stage": "evidence",
      "items": [
        {
          "evidence_name": "zabbix_triggers",
          "success": true,
          "data": {
            "triggers": [
              {
                "description": "Disk space critically low on /var",
                "priority": "4",
                "status": "PROBLEM"
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
from src.tool.zabbix import ZabbixTool
from src.tool.zabbix.client import ZabbixClient

client = ZabbixClient(
    base_url="https://zabbix.example.com/api_jsonrpc.php",
    username="api_user",
    password="api_password",
)
tool = ZabbixTool(client=client)
result = tool.execute({"capability": "hosts"})
print(result.data)
```

## Configuration

Secrets are stored in `config/secrets.local.json`:

```json
{
  "zabbix": {
    "base_url": "https://zabbix.example.com/api_jsonrpc.php",
    "username": "api_user",
    "password": "api_password"
  }
}
```

## Notes

- Uses Zabbix JSON-RPC API (v2.0+).
- All responses are formatted into consistent dict structures with string-based severity labels.
- Host search supports fuzzy matching.
- Event timeline queries default to 50 results, configurable via limit parameter.