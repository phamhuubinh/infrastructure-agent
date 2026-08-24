# Docker architecture

## Current Compose stack

The current `docker-compose.yml` defines:

```text
reverse-proxy
api
ui
postgres
rag-service
```

There is currently **no Qdrant service** in the Compose file.

## Current network exposure

Host-exposed endpoints currently include:

```text
reverse-proxy  127.0.0.1:80
api            127.0.0.1:61888
```

Internal container endpoints include:

```text
ui             3000
postgres       5432
rag-service    8080
```

The reverse proxy is the normal local Web entry point.

Do not document old development ports such as UI `5173`, API `8000`, RAG `8001`, or Qdrant `6333` as current Compose behavior unless the Compose file changes.

## Service relationships

```text
reverse-proxy
  ├── api
  ├── ui
  └── rag-service (health dependency)

api
  ├── postgres
  └── rag-service
```

The API uses a persistent `orion-data` volume; PostgreSQL uses `orion-pgdata`; RAG uses `orion-ragdata`.

## Current RAG deployment settings

The Compose configuration currently starts `rag-service` with:

```text
RAG_EMBEDDING_PROVIDER=hash
RAG_VECTOR_STORE=memory
RAG_RERANKER=noop
RAG_OCR_PROVIDER=noop
RAG_DATA_DIR=/data
```

This is current packaging configuration, not a restriction on the target RAG architecture.

## Start/build

```bash
docker compose up -d --build
```

The installer uses:

```bash
docker compose up -d --build --remove-orphans
```

## Status

```bash
docker compose ps
```

## Logs

All services:

```bash
docker compose logs -f
```

Specific services:

```bash
docker compose logs -f reverse-proxy
docker compose logs -f api
docker compose logs -f ui
docker compose logs -f postgres
docker compose logs -f rag-service
```

## Stop

```bash
docker compose down
```

Do not add `-v` unless you intentionally want to remove persistent volumes/data.

## Architecture relationship

Docker is packaging, not semantic architecture.

The target Chat/Project/model-tool loop should remain independent of whether components run in Compose, directly on the host, or in another local deployment layout.
