# Quickstart

This page documents the repository's **current** installation/run path. Target architecture behavior is documented separately under `docs/architecture/`.

## Requirements

Current `install.sh` expects a Linux-like host with:

- Docker Engine;
- Docker Compose;
- common account/group utilities such as `getent` and `groupadd`;
- permission to create/configure the Orion tool-secrets group/file (directly or through `sudo`).

Git and `curl` are useful for normal repository/development work.

## Install

From the repository root:

```bash
./install.sh
```

Current installer behavior:

```text
prepare .env
→ generate missing PostgreSQL/API secrets
→ create/configure external tool-credentials file
→ install the `orion` CLI
→ optionally prompt for an OpenAI-compatible model when stdin is interactive
→ docker compose up -d --build --remove-orphans
→ report tool credential status
```

The current script does **not** define documented `--non-interactive` or `--skip-up` command-line options.

When stdin is non-interactive, the optional model setup prompt is skipped automatically.

## Start/use the Web UI

After installation:

```bash
orion web
```

The wrapper ensures the Web-facing services are running, prints the configured Web URL, opens a browser when possible, and follows current API/UI logs.

Disable browser launch:

```bash
ORION_DISABLE_BROWSER=1 orion web
```

## Logs

```bash
orion log
```

or:

```bash
docker compose logs -f
```

## Service status

```bash
docker compose ps
```

## Current Compose service names

```text
reverse-proxy
api
ui
postgres
rag-service
```

## Development checks

Use repository targets that exist in the current checkout. Common commands are:

```bash
make test
make lint
```

Frontend tests, when applicable:

```bash
cd ui
npm test
```

## Target Chat/Project behavior

The target runtime remains:

```text
message
→ model with all registered tools
→ direct answer OR automatic model-selected tool call
→ Orion executes the registered tool
→ ToolResult back to the same model
→ repeat as useful
→ final answer
```

There is no manual tool selection step in Chat or Project.
