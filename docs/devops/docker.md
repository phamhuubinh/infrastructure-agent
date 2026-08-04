# Docker Compose

The root Compose stack runs the React UI, FastAPI API, PostgreSQL, the project RAG service, and an HTTP reverse proxy for local use. Model servers are user-managed external dependencies; Orion does not install model runtimes or weights.

## Quick start

```bash
./install.sh
docker compose ps
orion help
```

The installer creates `.env` with private random secrets, initializes `/etc/orion/tool-credentials.json` as an empty private file when absent, reports missing Grafana/Zabbix fields, installs a lightweight `~/.local/bin/orion` launcher, starts every Orion component, and optionally configures an existing model endpoint. Grafana/Zabbix and model setup may both be skipped. The launcher executes the packaged CLI inside the API container, so no host Python environment is required. Open `http://localhost`; the reverse proxy supplies the internal API credential, so the packaged Web UI needs no manual API-key entry. Local Compose uses HTTP; terminate TLS in a production ingress/reverse proxy.

`orion web` starts the packaged Web services when needed, opens the Web UI, and follows only API/UI logs generated from that invocation onward. `Ctrl+C` stops those Web services. On SSH/headless systems it prints the URL instead of opening a browser. It does not start a second backend or a Vite development server inside the API container. `orion log` follows logs from all Compose services; `Ctrl+C` exits that viewer without stopping Orion.

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

`docker compose down` preserves these volumes. `docker compose down -v` deletes Compose-managed persisted data and cannot be undone. The supported `./uninstall.sh` flow performs the complete cleanup, including legacy volumes and host-side private files.

## Generated environment

`install.sh` creates `.env` automatically. `.env.example` documents its shape for operators running Compose directly:

```dotenv
POSTGRES_USER=orion
POSTGRES_PASSWORD=replace-with-a-long-random-password
POSTGRES_DB=orion
ORION_API_KEY=replace-with-a-long-random-api-key
ORION_TOOL_SECRETS_FILE=/etc/orion/tool-credentials.json
```

`POSTGRES_PASSWORD` and `ORION_API_KEY` are required; Compose refuses blank values. The ignored legacy `docker-compose.env` file is not required.

## Grafana and Zabbix credentials

The tracked `tools.json` contains only safe tool metadata and is copied into the API image. Deployment-specific URLs and tokens belong in `/etc/orion/tool-credentials.json`, outside the checkout. Compose mounts that file read-only at `/run/secrets/orion-tool-credentials.json`; it is never copied into an image. `ORION_TOOL_SECRETS_FILE` can override the host path, but it must remain absolute.

For a new installation, the recommended flow is:

1. Create a dedicated read-only service-account/API token in Grafana and Zabbix.
2. Copy an existing credential file to `/etc/orion/tool-credentials.json` through a secure channel, or enter the endpoints and tokens using `config/tool-credentials.example.json` as a reference.
3. Keep the file readable only by the installation account (`0600`). The installer applies this mode when it creates the file.
4. Run `./install.sh`. If the file is absent, installation continues with an empty private file and both tools disabled. If Orion was already running, use `docker compose up -d --force-recreate api` after changing credentials so Compose remounts the secret file.

The same token may be reused by securely transferring `/etc/orion/tool-credentials.json`, but separate tokens per Orion installation are easier to revoke and audit. Orion does not create external service tokens automatically because doing so would require storing Grafana/Zabbix administrative credentials. An empty `{}` file is valid and leaves both tools disabled; the installer reports each missing `url`/`token` field.

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
orion web
orion log
docker compose build api ui rag-service
docker compose up -d api ui rag-service
docker compose exec postgres pg_isready -U orion
docker compose exec reverse-proxy nginx -t
```

The API image seeds an empty model registry. Model credentials are written to the private persistent Orion volume, never to the tracked repository configuration. Grafana/Zabbix credentials remain in the system-wide host file and are mounted read-only.

## Uninstall

`./uninstall.sh` is intentionally destructive: after a `y/yes` confirmation it removes the running app, Orion-built images, every current/legacy Orion volume, model connections, sessions, RAG documents/indexes, logs, `.env`, legacy private configuration, the CLI launcher, and legacy Ollama artifacts created by older Orion versions. It then asks separately whether `/etc/orion/tool-credentials.json` should be removed; `n/no` preserves it. `./uninstall.sh --yes` performs non-interactive runtime cleanup and always preserves the shared credential file; use `./uninstall.sh --dry-run` to inspect the actions. The source checkout and independently operated external model runtimes are never deleted. A later `./install.sh` gets empty data stores and newly generated runtime secrets while reusing retained monitoring credentials.

> Last updated: 2026-08-02
