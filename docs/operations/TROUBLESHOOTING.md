# Troubleshooting

## Orion does not start

```bash
docker compose ps
docker compose logs --tail=200
```

Rebuild if required:

```bash
docker compose up -d --build
```

## CLI says Orion is not running

Check API:

```bash
docker compose ps
docker compose logs --tail=200 api
```

The current `orion` wrapper expects the API service to be running for ordinary CLI commands.

## Web UI unavailable

```bash
docker compose ps
docker compose logs --tail=200 ui
docker compose logs --tail=200 api
```

## Model unavailable

Check:

- configured base URL;
- served model ID;
- network reachability from the API container;
- provider-compatible API;
- authentication if required.

## Model never calls tools

Check:

1. the tool is registered;
2. the model call actually includes the tool schema;
3. provider adapter supports tool calls;
4. system prompt does not prohibit tools;
5. ToolResult messages use provider-valid format.

Do **not** solve this by adding hard-coded prompt keyword routing.

## RAG returns no project results

Check:

```text
active project ID
document ingestion state
project/source metadata
embedding/index health
Qdrant
query filters
```

Project source filtering must be exact.

## Integration failures

Inspect tool-specific logs/config for:

- Linux target connectivity/credentials;
- Grafana endpoint/token;
- Zabbix endpoint/token;
- Internet connectivity.

Tool failures should return to the model as errors rather than be silently converted to empty success.
