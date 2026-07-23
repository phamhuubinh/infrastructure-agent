# 08 - Project State
> Source of truth for "what actually exists." If this file and any other doc disagree, this file wins (see `00_BOOTSTRAP.md`). Update this file whenever status changes — do not let it drift from reality (`07_DEVELOPMENT_RULES.md`, rule 25).

## Phase
**Local MVP with Docker Compose.** Single-user, single-machine, no network exposure beyond outbound calls to targets/Grafana/Zabbix/LLM APIs. WP1 local infrastructure (Docker Compose, nginx reverse proxy, PostgreSQL, self-signed HTTPS) is in place.

## Implemented
- Deterministic pipeline: Intent Resolution → Target Resolution → Evidence Planning → Capability Resolution → Execution Planning → Execution Graph → Execution Runtime (`src/pipeline/*`).
- `KnowledgeTool` as the single dispatch entry point to Child Tools (`src/tool/knowledge_tool.py`).
- Child Tools: `LinuxTool` (SSH execution via `execution_backend.py`), `GrafanaTool`, `ZabbixTool`, `InternetTool` (HTTP fetch with SSRF protection), `KnowledgeBaseTool` (RAG service proxy).
- Local target registry backed by a JSON file (`src/tool/target_registry.py`, `target_store.py`).
- Assessment layer: `LLMAssessmentAdapter` (real) and `MockAssessmentAdapter` (offline/dev), behind the `AssessmentModelAdapter` interface (`src/model/*`).
- CLI entry point with local mode and `--web` mode (`src/cli.py`).
- Web UI (TanStack Start / React) for local dev use (`ui/`), talking to the local backend started by `--web`.
- Step-by-step pipeline visualization in Web UI (intent → evidence → prompt → assessment with expandable details).
- Web UI `/api/query` returns full `steps` array with intent, confidence, evidence items, runtime metrics, token usage.
- Chat interface with routing: keyword match + model classify to distinguish infrastructure queries from general chat.
- Fuzzy target name matching for typo-tolerant server resolution.
- Deterministic responder (`src/pipeline/deterministic_responder.py`) — generates responses without LLM for simple evidence (service status, zombie processes) before the full assessment step.
- Capability reference model (`src/pipeline/capability_reference.py`) — typed dataclass for capability references across the pipeline.
- Assessment request model (`src/pipeline/assessment_request.py`) — typed request envelope used by `AssessmentAdapter`.
- Ctrl+C cancel support without crash.
- Benchmark runner (`python -m benchmark`) with dataset, scoring, reporting, regression detection, CSV/Markdown/JSON export, and configurable repeat runs (`benchmark/`).
- RAG microservice (`src/tool/RAGTool/`) with embedding, vector store, OCR, document parsing, query expansion, reranking, fusion, chunking, GraphRAG/LightRAG support, and a full query/ingest pipeline.
- Test suite: **859 tests** across pipeline, tools, model, backend, agent, and benchmark modules.
- Docker Compose deployment (local): nginx reverse proxy with HTTPS (self-signed cert), FastAPI API, React UI, PostgreSQL database (`docker-compose.yml`).
- Dify conversational layer (`src/backend/dify_client.py`, `src/backend/dify_setup.py`): Dify API/Web Docker services with auto-setup (app creation, API key generation, dataset creation) and API proxy endpoints (`/api/dify/health`, `/api/dify/chat`, `/api/dify/knowledge/query`).
- Desktop App (`desktop/`): Electron wrapper for the Web UI. Serves the built TanStack Start SSR app from an embedded Node.js server and proxies `/api` calls to `127.0.0.1:61888`. Launch with `make desktop-start` (requires `make desktop-install` first).

## WP4: Platform capability migration (in progress)
- Agent runs as a platform capability via the FastAPI API (`src/backend/api.py` as uvicorn entry point).
- PostgreSQL session store (`src/backend/db.py`) with `PostgresConversationStore` replacing JSON file storage when `ORION_DATABASE_URL` is set.
- `psycopg2-binary` dependency added to `pyproject.toml`.
- Docker Compose API service configured with `ORION_DATABASE_URL` environment variable.
- Fallback to JSON file storage when no database URL is configured (backward compatible).
- API authentication via optional `ORION_API_KEY` env var (`src/backend/auth.py`), with `APIKeyMiddleware` protecting all endpoints except `/api/health`. Default: disabled (no key required in local mode).
- Basic document upload/list/delete (`src/backend/document_service.py`, `src/backend/routers/documents.py`) with filesystem storage under `~/.orion/documents/` and optional PostgreSQL metadata. Full document service (preview, search, versioning, Knowledge Base integration) is not implemented.
- FastAPI dependency injection (`src/backend/dependencies.py`) — shared session and conversation store dependencies for API routes.

## Security scanning added to CI
- **Bandit** static analysis runs on `src/` in CI, configured via `pyproject.toml` with known-issue skips.
- **Safety** checks dependencies for known vulnerabilities (continues on error — advisory only).
- **pip-audit** scans installed packages for known CVEs.
- `make security-scan` target added; `make ci` now includes `security-scan`.
- New optional dependency group `[security]` (`bandit>=1.7`, `safety>=3.0`, `pip-audit>=2.7`).

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
- **Multi-user accounts** — no login/password system, no user registration. Optional API key auth (`ORION_API_KEY`) exists for single-tenant protection.
- **Remote hosting** — no remote deployment yet. `docker-compose.yml` provides local Docker Compose with nginx reverse proxy and self-signed HTTPS.
- **Production SSR deployment** — TanStack Start SSR requires Nitro runtime; `--web` mode runs in dev mode with Vite.

## Known issues / open items being tracked
- **SSH host key checking** is currently disabled by design for the local trusted-network use case — this is an intentional trade-off, recorded in `09_ARCHITECTURE_DECISIONS.md`, not an oversight.
- **Dependency reconciliation**: `pyproject.toml` dependencies have been partially reconciled. Third-party packages that are actually imported are declared; unused declarations (`numpy`, `requests`) remain as placeholders pending removal.
- **Frontend-backend session sync** (fixed 2026-07-23): Frontend ChatProvider now fetches sessions from `GET /api/sessions` on mount, creates sessions server-side via `POST /api/sessions`, and sends `session_id` with every `/api/query` request. Previously sessions existed only in local React state with generated IDs, causing the Orion Web session list to show zero sessions and sessions created in Orion Web to be invisible in the sidebar.
- **CLI session persistence** (fixed 2026-07-23): CLI `_run_agent()` now creates a `ConversationStore` with a UUID session ID (or resume ID) and passes it to `create_deterministic_agent()`. Previously `conversation_store=None`, so `DeterministicAgent._conversation_store` was `None` and `add_turn()` was never called.
- **Session metadata corruption** (fixed 2026-07-23): Four bugs compounded to corrupt session metadata when opening from the Web UI: (1) `_check_compress()` counted classifier messages (`[classified as ...]`) as real turns, causing premature summarization that cleared `_mem` entirely, (2) `ConversationStore._save()` never wrote `title` to disk, (3) `ConversationStore._load()` never restored `source` from disk (hardcoded `"api"`), (4) `chat-store.tsx` ignored server titles. Fixed: classifier messages excluded from turn counts, `title` saved/loaded, `source` restored from persisted data, frontend reads server titles.

## Phase 1 — Foundation (completed 2026-07-22)
- ID 87: Replaced broad `except Exception` in execution_runtime.py with specific exception types (`RuntimeError`, `ValueError`, `TypeError`, `OSError`, `CancelledError`).
- ID 88: Thread-safe database connection pool with semaphore-based concurrency (max 5, configurable via `ORION_DB_POOL_SIZE`). Connection reuse across requests instead of per-request creation.
- ID 89: Removed duplicate tool execution logic — `GrafanaTool`, `ZabbixTool`, `InternetTool`, `KnowledgeBaseTool` now delegate to shared `_dispatch()` in base `Tool` class.
- ID 90: Standardized tool interface — base `Tool` provides `_resolve_capability()`, `_filter_arguments()`, and `_dispatch()` helpers. Consistent error messages and argument filtering across all tools.
- ID 55: Thread Safety Tests for Execution Runtime and Tool execution — 30 tests across 3 modules.

## Phase 2 — Quality & Technical Debt (completed 2026-07-23)
All 53 Phase 2 tasks completed across 6 epics:
- **Core Architecture** (7/7): Safe data serialization with nested/circular support, EvidencePlanner fallback, configurable conversation threshold, configurable frontend port, dead code removal, /proc read caching, internal error detail hiding.
- **Security** (11/11): Error message sanitization, file upload validation, path traversal prevention, log masking, global mutable secret state removal, rate limiting, upload size limits, local file access restriction, database credential masking, session ID validation, security regression tests.
- **DevOps & CI/CD** (5/5): Dependabot configuration, graceful shutdown, UI test stage in CI, improved logging (file rotation + structured JSON), monitoring metrics endpoint.
- **Testing & QA** (11/11): Shared pytest fixtures, benchmark-to-dataset conversion, serialization/upload/internet/knowledge/capability tests, performance benchmarks, memory leak tests, load tests, test coverage improvement.
- **Documentation** (9/9): CONTRIBUTING.md expansion, SECURITY.md improvements, issue templates, last-updated metadata, benchmark report consolidation, documentation standardization, bootstrap guide, development rules update, project state update.
- **Code Quality** (10/10): Hardcoded config removal, config system standardization, logging consistency, error handling strategy, runtime performance, capability resolution refactoring, response model standardization, type hints, legacy code removal, project structure standardization.
- ID 243: CI security scans now fail on high-severity CVE findings (`--audit-level=high` for Safety, `--fail-on=high` for pip-audit).

## Phase 3 — Polish & Governance (completed 2026-07-23)
All 19 Phase 3 tasks completed across 4 epics:
- **Core Architecture** (1/1): Naming conventions verified consistent across all modules.
- **DevOps & CI/CD** (6/6): Resource limits documented, deployment pipeline and release automation documented, CI caching and parallelism verified, dev environment standardized, comprehensive DevOps documentation created (`docs/devops/`).
- **Testing & QA** (4/4): Benchmark reports documented, duplicate test audit (0 found), test documentation created (`docs/testing/README.md`), continuous quality monitoring via MetricsCollector + CI artifacts.
- **Documentation** (4/4): Tool documentation (5 tools), API documentation (13 endpoints), architecture diagrams (5 Mermaid diagrams), documentation consistency review completed.
- **Code Quality** (4/4): Technical debt review (0 findings), duplicate utility audit (0 found), coding style verified (ruff clean), final architecture cleanup confirmed.

## Documentation created this phase
| Doc | Path |
|-----|------|
| Linux Tool | `docs/tools/linux.md` |
| Grafana Tool | `docs/tools/grafana.md` |
| Zabbix Tool | `docs/tools/zabbix.md` |
| Internet Tool | `docs/tools/internet.md` |
| Knowledge Base Tool | `docs/tools/knowledge-base.md` |
| API Reference | `docs/api/README.md` |
| Architecture Diagrams | `docs/architecture/diagrams.md` |
| Docker Guide | `docs/devops/docker.md` |
| CI/CD Guide | `docs/devops/ci.md` |
| Testing Guide | `docs/testing/README.md` |

## Next milestones
1. All 105 backlog tasks complete (Phases 0–3). Backlog is empty.
2. WP1 (`04_ROADMAP.md`) begins once public VM access is available — not before.

> **Last updated:** 2026-07-23.
