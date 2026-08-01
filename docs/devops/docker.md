# Docker Compose

The root Compose stack runs the React UI, FastAPI API, PostgreSQL, the project RAG service, and an HTTP reverse proxy for local use. Model servers are user-managed external dependencies; Orion does not install model runtimes or weights.

## Quick start

```bash
./install.sh
docker compose ps
orion help
```

The installer creates `.env` with private random secrets, installs a lightweight `~/.local/bin/orion` launcher, starts every Orion component, and optionally configures an existing model endpoint. Choosing **Skip** is supported. The launcher executes the packaged CLI inside the API container, so no host Python environment is required. Open `http://localhost`; the reverse proxy supplies the internal API credential, so the packaged Web UI needs no manual API-key entry. Local Compose uses HTTP; terminate TLS in a production ingress/reverse proxy.

`orion web` opens the packaged Web UI URL in the default desktop browser. On SSH/headless systems it prints the URL. It does not start a second backend or a Vite development server inside the API container.

| Service | Internal port | Host exposure | Purpose |
|---|---:|---:|---|
| `reverse-proxy` | 80 | 80 | Browser entry point |
| `api` | 61888 | 61888 | API/debug access and CI smoke tests |
| `ui` | 3000 | none | TanStack Start SSR frontend behind proxy |
| `postgres` | 5432 | none | Chat/document metadata |
| `rag-service` | 8080 | none | Internal project RAG API |

The RAG service is deliberately not published. Browser traffic goes through `/api/rag/*`, so backend authentication and upload limits always apply.

## Persistence

- `orion-data:/root/.orion` — SQLite fallback and generic document storage.
- `orion-pgdata:/var/lib/postgresql/data` — PostgreSQL.
- `orion-ragdata:/data` — RAG project metadata, uploaded corpus, vector data, and BM25 indexes.

`docker compose down` preserves these volumes. `docker compose down -v` deletes all persisted local data and cannot be undone.

## Generated environment

`install.sh` creates `.env` automatically. `.env.example` documents its shape for operators running Compose directly:

```dotenv
POSTGRES_USER=orion
POSTGRES_PASSWORD=replace-with-a-long-random-password
POSTGRES_DB=orion
ORION_API_KEY=replace-with-a-long-random-api-key
```

`POSTGRES_PASSWORD` and `ORION_API_KEY` are required; Compose refuses blank values. The ignored legacy `docker-compose.env` file is not required.

## Model lifecycle

Model weights and external credentials are not required to install Orion. Configure them later from Web UI **Cài đặt** or CLI:

```bash
docker compose exec api orion model list
docker compose exec api orion model add primary --base-url http://model-host:8000 --model qwen
docker compose exec api orion model test primary
docker compose exec api orion model use primary
```

The model registry is persisted in `orion-data`. Changes made by the CLI are detected by the running API without a restart. Chat uses the model selected per request; RAG synthesis always uses Orion's active model and never falls back to retrieval-only output. OpenAI-compatible, Ollama, and vLLM endpoints are supported when installed and operated independently by the user.

The Compose API maps `host.docker.internal` to the Docker host. When a saved model URL uses `localhost`, `127.0.0.1`, or `::1`, Orion rewrites only that loopback host to `host.docker.internal`; this lets a user-managed model runtime on the same machine work without exposing it publicly.

RAG retrieval itself uses bundled hash embeddings, persistent vectors, BM25, and a no-op reranker by default. For larger deployments, configure an OpenAI-compatible embedding endpoint and optionally Qdrant; see `src/tool/RAGTool/README.md`.

## Common commands

```bash
docker compose logs -f api rag-service
docker compose build api ui rag-service
docker compose up -d api ui rag-service
docker compose exec postgres pg_isready -U orion
docker compose exec reverse-proxy nginx -t
```

The API image seeds an empty model registry. Model credentials are written to the private persistent Orion volume, never to the tracked repository configuration.

## Uninstall

`./uninstall.sh` removes the running app and Orion-built images while preserving persistent data. `./uninstall.sh --purge` also deletes Orion volumes, local sessions/documents/logs, `.env`, private local configuration, and legacy Ollama artifacts created by older Orion versions. The source checkout is never deleted.

> Last updated: 2026-08-02
