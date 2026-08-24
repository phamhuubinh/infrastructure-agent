# Running Orion locally

## Web UI

```bash
orion web
```

Current CLI behavior:

- starts the Web-facing Docker services;
- prints the Web URL;
- opens a browser when a graphical desktop is available;
- follows API/UI logs;
- Ctrl+C stops the Web-facing services started for that command.

Disable automatic browser opening:

```bash
ORION_DISABLE_BROWSER=1 orion web
```

Override URL shown/opened:

```bash
ORION_WEB_URL=http://localhost orion web
```

## Logs

```bash
orion log
```

This follows all Compose logs while services continue to run.

## Docker status

```bash
docker compose ps
```

## Direct Compose lifecycle

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

## CLI commands

When the API container is running, the installed `orion` wrapper forwards non-Web commands into the API container.

Use:

```bash
orion --help
```

to inspect the current CLI surface.

## Target runtime

Running locally does not change Chat/Project semantics:

```text
UI/CLI
→ backend
→ local/remote configured model
→ automatic registered tool calls
→ local integrations/RAG
→ final response
```
