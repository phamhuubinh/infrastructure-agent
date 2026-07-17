# 08 - Project State
> Source of truth for "what actually exists." If this file and any other doc disagree, this file wins (see `00_BOOTSTRAP.md`). Update this file whenever status changes — do not let it drift from reality (`07_DEVELOPMENT_RULES.md`, rule 25).

## Phase
**Local MVP with Docker Compose.** Single-user, single-machine, no network exposure beyond outbound calls to targets/Grafana/Zabbix/LLM APIs. WP1 local infrastructure (Docker Compose, nginx reverse proxy, PostgreSQL, self-signed HTTPS) is in place.

## Implemented
- Deterministic pipeline: Intent Resolution → Target Resolution → Evidence Planning → Execution Graph → Execution Runtime (`src/pipeline/*`).
- `KnowledgeTool` as the single dispatch entry point to Child Tools (`src/tool/knowledge_tool.py`).
- Child Tools: `LinuxTool` (SSH execution via `execution_backend.py`), `GrafanaTool`, `ZabbixTool`.
- Local target registry backed by a JSON file (`src/tool/target_registry.py`, `target_store.py`).
- Assessment layer: `LLMAssessmentAdapter` (real) and `MockAssessmentAdapter` (offline/dev), behind the `AssessmentModelAdapter` interface (`src/model/*`).
- CLI entry point with local mode and `--web` mode (`src/cli.py`).
- Web UI (TanStack Start / React) for local dev use (`ui/`), talking to the local backend started by `--web`.
- Step-by-step pipeline visualization in Web UI (intent → evidence → prompt → assessment with expandable details).
- Web UI `/api/query` returns full `steps` array with intent, confidence, evidence items, runtime metrics, token usage.
- Chat interface with routing: keyword match + model classify to distinguish infrastructure queries from general chat.
- Fuzzy target name matching for typo-tolerant server resolution.
- Ctrl+C cancel support without crash.
- Benchmark runner (`python -m benchmark`) with dataset, scoring, reporting, regression detection, CSV/Markdown/JSON export, and configurable repeat runs (`benchmark/`).
- RAG microservice (`src/tool/RAGTool/`) with embedding, vector store, OCR, document parsing, query expansion, reranking, fusion, chunking, GraphRAG/LightRAG support, and a full query/ingest pipeline.
- Test directory (`tests/`) with pipeline and tool tests.
- Docker Compose deployment (local): nginx reverse proxy with HTTPS (self-signed cert), FastAPI API, React UI, PostgreSQL database (`docker-compose.yml`).
- Dify conversational layer (`src/backend/dify_client.py`, `src/backend/dify_setup.py`): Dify API/Web Docker services with auto-setup (app creation, API key generation, dataset creation) and API proxy endpoints (`/api/dify/health`, `/api/dify/chat`, `/api/dify/knowledge/query`).
- Desktop App (`desktop/`): Electron wrapper for the Web UI. Serves the built TanStack Start SSR app from an embedded Node.js server and proxies `/api` calls to `127.0.0.1:61888`. Launch with `make desktop-start`.

## WP4: Platform capability migration (in progress)
- Agent runs as a platform capability via the FastAPI API (`src/backend/api.py` as uvicorn entry point).
- PostgreSQL session store (`src/backend/db.py`) with `PostgresConversationStore` replacing JSON file storage when `ORION_DATABASE_URL` is set.
- `psycopg2-binary` dependency added to `pyproject.toml`.
- Docker Compose API service configured with `ORION_DATABASE_URL` environment variable.
- Fallback to JSON file storage when no database URL is configured (backward compatible).

## Cleanup completed (stabilization phase)
- Removed dead code: `main.py`, `dump_assessment.py`, `api_server.py` (duplicate of `cli.py`).
- Removed empty `__init__.py` files (PEP 420 namespace packages).
- Removed stale `docs/engineering/` legacy architecture docs.
- Removed Lovable branding: AGENTS.md, .lovable/, lovable-error-reporting, vite config dependency.
- Replaced `@lovable.dev/vite-tanstack-config` with direct standard plugin imports.
- Removed `--store` deprecated CLI flag.
- Removed debug `print()` statements from tool files.
- Removed unused Python imports.
- Updated README.md and HTML metadata.

## Not implemented (do not assume otherwise)
- **Authentication / accounts** — no login, no sessions.
- **Remote hosting** — no remote deployment yet.
- **Document Service** — not implemented.
- **Desktop App** — Electron wrapper implemented (`desktop/`). Serves the existing TanStack Start SSR UI via embedded Node.js server, proxies `/api` calls to the backend at `127.0.0.1:61888`. Launch with `make desktop-start` (requires `make desktop-install` first).
- **Internet Tool** — planned for WP4, opt-in-only when built (see `04_ROADMAP.md`).
- **Production SSR deployment** — TanStack Start SSR requires Nitro runtime; `--web` mode runs in dev mode with Vite.

## Known issues / open items being tracked
- **SSH host key checking** is currently disabled by design for the local trusted-network use case — this is an intentional trade-off, recorded in `09_ARCHITECTURE_DECISIONS.md`, not an oversight.
- **Dependency reconciliation**: `pyproject.toml` dependencies have been partially reconciled. Third-party packages that are actually imported are declared; unused declarations (`numpy`, `requests`) remain as placeholders pending removal.

## Next milestones
1. Complete code quality improvements (lint fixes, test coverage for untested modules).
2. WP1 (`04_ROADMAP.md`) begins once public VM access is available — not before.
