# Assessment Configuration

## servers.json

Model server configuration is stored in `servers.json` at the repository root.

```json
{
  "active_server": "sv1",
  "servers": {
    "sv1": {
      "provider": "openai",
      "base_url": "http://192.168.90.240:8000",
      "model": "deepseek-ai/DeepSeek-V4-Flash",
      "api_key": null,
      "timeout": 60,
      "temperature": 0.0,
      "max_tokens": 2048
    }
  }
}
```

## Fields

| Field | Required | Default | Description |
|---|---|---|---|
| `provider` | Yes | — | Must be `openai` (compatible) |
| `base_url` | Yes | — | OpenAI-compatible API endpoint |
| `model` | Yes | — | Model name |
| `api_key` | No | null | API key for authentication |
| `timeout` | No | 60 | HTTP timeout in seconds |
| `temperature` | No | 0.0 | Model temperature (0.0 = deterministic) |
| `max_tokens` | No | 2048 | Maximum response tokens |

## CLI Override

```
python -m src.cli --server sv1 --model gpt-4
```

- `--server` selects a server config from `servers.json`
- `--model` overrides the model name (optional)
- Default: mock assessment (no LLM call)

## No Assessment Logic in Config

Configuration contains only connection details.
No prompt templates, no assessment rules, no investigation logic.
