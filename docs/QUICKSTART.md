# Quickstart

This page covers the current repository packaging while the codebase moves toward the target architecture.

## Requirements

The installer expects:

- Docker Engine;
- Docker Compose;
- Git;
- `curl` is useful for health checks.

## Install

From the repository root:

```bash
./install.sh
```

Non-interactive installation:

```bash
./install.sh --non-interactive
```

The installer creates `.env` from `.env.example` when necessary, generates missing local secrets, builds the Docker services, and installs the `orion` CLI under the configured install prefix.

## Start Web UI

```bash
orion web
```

The CLI starts the Web-facing services and opens the configured URL when a desktop browser is available.

To disable browser launch:

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

## Development checks

```bash
make test
make lint
```

Frontend tests:

```bash
cd ui
npm test
```

## Architecture behavior

Once the target runtime is implemented, Chat and Project should both behave this way:

```text
message
→ model
→ direct answer OR automatic tool call
→ Orion executes tool
→ tool result back to model
→ repeat as useful
→ final answer
```

No manual tool selection step exists.
