# Docker architecture

## Current stack

The repository's Compose deployment contains local services for:

- PostgreSQL;
- Qdrant;
- RAG service;
- API/backend;
- UI/reverse proxy components.

Default development/service ports currently include:

```text
UI:     5173
API:    8000
RAG:    8001
Qdrant: 6333
```

Actual external exposure can be changed by Compose/environment configuration.

## Start

```bash
docker compose up -d --build
```

## Status

```bash
docker compose ps
```

## Logs

```bash
docker compose logs -f
```

Specific service:

```bash
docker compose logs -f api
docker compose logs -f rag
docker compose logs -f ui
```

## Stop

```bash
docker compose down
```

Do not add `-v` unless you intentionally want to remove persistent volumes/data.

## Build

```bash
make docker-build
```

## Architecture relationship

Docker is packaging, not the semantic architecture.

The target Chat/Project/model-tool loop should work regardless of whether components run in Compose, directly on the host, or in another local deployment layout.
