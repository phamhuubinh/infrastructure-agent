# 08 - Project State
> Source of truth for "what actually exists." If this file and any other doc disagree, this file wins (see `00_BOOTSTRAP.md`). Update this file whenever status changes — do not let it drift from reality (`07_DEVELOPMENT_RULES.md`, rule 25).

## Phase
**Local MVP with Docker Compose.** Single-user, single-machine. Docker Compose provides an HTTP reverse proxy for local use; production TLS is expected to terminate outside this stack.

## Implemented
- 6-stage deterministic pipeline: Normalize → Target → Plan → Graph → Execute → Assess (`src/pipeline/*`). A canonical immutable `RequestFrame` carries concepts/operation/target/params/answer type/timeframe and ranked ambiguity evidence through routing; CapabilityPlanner maps concept+action via `config/capability_plans.yaml`.
- `KnowledgeTool` as the single dispatch entry point to Child Tools (`src/tool/knowledge_tool.py`).
- Chat Child Tools: `LinuxTool` (SSH execution via `execution_backend.py`), `GrafanaTool`, `ZabbixTool`, and `InternetTool`. Internet has bounded `web_fetch` plus provider-neutral `web_search`, both behind the same public-URL/SSRF boundary. RAG is explicitly excluded from chat registration.
- Local target registry backed by a JSON file (`src/tool/target_registry.py`, `target_store.py`).
- Assessment layer: `LLMAssessmentAdapter` (real), `MockAssessmentAdapter` (tests), and an explicit unconfigured/setup adapter, behind the `AssessmentModelAdapter` interface (`src/model/*`). Orion starts without a model.
- CLI entry point with local mode, `web` mode, and model management (`src/cli/main.py`).
- Web UI (TanStack Start / React) with isolated Chat sessions, a dedicated project-based document-analysis page, API-key settings, and model add/install/test/select/delete controls. Docker packages its Nitro SSR server as the `ui` service; source development uses Vite.
- Step-by-step pipeline visualization in Web UI (intent → evidence → prompt → assessment with expandable details).
- Web UI `/api/query` returns full `steps` array with intent, confidence, evidence items, runtime metrics, token usage.
- Chat interface with fully deterministic routing statuses; no model classifier participates in infrastructure routing. General chat remains a separate model-backed subsystem.
- General-agent routing v1: immutable `RequestFrame` semantics distinguish stable general knowledge, live environment inspection, current external information, explicit URLs, typed source constraints, and explain/generate/inspect/mutate intent. Stable/general and content-generation requests do not run collectors; actual mutations remain refused.
- Deterministic external verification: current/explicit-online requests use a bounded `web_search → select → web_fetch → EvidencePackage/Fact` path. The model receives evidence only, never tool authority. Current answers render source URL/retrieval time; unavailable verification returns an explicit unverified/UNKNOWN response rather than stale model memory.
- Typed source constraints (`Grafana only`, `Zabbix only`, `SSH only`, Internet/URL-only and exclusions) are enforced before capability planning. Exact source unavailability fails closed and runtime provenance is preserved rather than relabelled.
- External verification has request budgets, short-lived valid-only caching, public-URL redirect/DNS validation, provider/query/freshness keys, and credential-safe provenance. API query responses expose additive credential-safe `trace_id` and `execution_trace` fields for QA/UI consumers.
- Target resolution uses exact/scoped aliases before fuzzy matching and requires both score threshold and candidate margin; explicit unknown/ambiguous targets clarify without localhost execution.
- Per-session `SessionInvestigationContext` persists only resolved target/concept/service/path/time semantics and incident IDs; deterministic follow-up resolution runs before target/capability planning, with explicit current targets taking precedence.
- Capability parameters are selected, bound and validated from child-tool `ParameterSpec` metadata before dispatch. Missing required values clarify; invalid/injection values fail closed; traces expose safe extracted/bound arguments.
- Coordinated requests are decomposed into at most four subframes with shared target/timeframe, merged evidence contracts and deduplicated parallel capabilities; broader requests ask the user to narrow scope.
- Canonical timezone-aware `TimeRange` distinguishes historical/comparison/forecast requirements. `TemporalEvidenceGuard` rejects comparison from fewer than two compatible windows and forecast without a sufficiently long series plus defined growth model before any model response.
- Deterministic responder (`src/pipeline/deterministic_responder.py`) — generates responses without LLM for simple evidence (service status, zombie processes) before the full assessment step.
- Capability reference model (`src/pipeline/capability_reference.py`) — typed dataclass for capability references across the pipeline.
- Assessment request model (`src/pipeline/assessment_request.py`) — typed request envelope used by `AssessmentAdapter`.
- Ctrl+C cancel support without crash.
- Benchmark runner (`python -m benchmark`) with dataset, scoring, reporting, regression detection, CSV/Markdown/JSON export, and configurable repeat runs (`benchmark/`).
- RAG microservice (`src/tool/RAGTool/`) with persistent project metadata, project-specific documents/vector collections/BM25 indexes, and bounded analysis history. Analysis always uses Orion's active model; retrieval-only output is not supported.
- Session isolation: each chat session owns its Agent, conversation store, evidence cache, and execution lock. Switching a model in one session cannot mutate another session.
- CI runs the Python suite and type-check, the independent locked RAG suite, UI lint/Vitest/build, Desktop proxy/package validation, security scans, image builds, and Compose smoke tests.
- Unified retry policy: `src/pipeline/retry.py` with `RetryPolicy` dataclass + `RetryExecutor` (exponential backoff + jitter), integrated into `ExecutionRuntime` tool dispatch and `db.py` database connection retry.
- Complete local installer (`install.sh`) and Docker Compose deployment: nginx HTTP reverse proxy, FastAPI API, React UI, PostgreSQL, and an internal-only persistent RAG service. The host launcher keeps `orion web` attached only to current API/UI logs and stops those Web services on `Ctrl+C`; `orion log` follows every Compose service without stopping them. The safe `tools.json` registry is packaged with the API while the system-wide `/etc/orion/tool-credentials.json` is mounted read-only as a Compose secret; installation reports missing credentials per tool. Model selection is prompted but optional; CLI and Web UI configure and test user-managed endpoints without installing model runtimes or weights. Uninstall always removes Orion runtime state (volumes, model registry, sessions, RAG data, logs, runtime secrets, and launcher) while preserving the source checkout and independently operated external model runtimes. Interactive uninstall separately offers to remove the shared Grafana/Zabbix credential file; non-interactive `--yes` preserves it.
- Desktop App (`desktop/`): Electron wrapper for a running Docker Orion installation. Serves the built TanStack Start SSR app from an embedded Node.js server and proxies `/api` calls to `127.0.0.1:80`, so nginx injects the packaged API key. It does not start a backend; launch with `make desktop-start` after the Docker stack is running (and `make desktop-install` on first use).

## WP4: Platform capability migration (in progress)
- Agent runs as a platform capability via the FastAPI API (`src/backend/api.py` as uvicorn entry point).
- PostgreSQL session store (`src/backend/db.py`) with `PostgresConversationStore` replacing JSON file storage when `ORION_DATABASE_URL` is set.
- `psycopg2-binary` dependency added to `pyproject.toml`.
- Docker Compose API service configured with `ORION_DATABASE_URL` environment variable.
- SQLite session storage at `~/.orion/sessions.db` when no database URL is configured.
- API authentication via optional `ORION_API_KEY` env var (`src/backend/auth.py`), with `APIKeyMiddleware` protecting all endpoints except `/api/health`. Default: disabled (no key required in local mode).
- Legacy generic document upload/list/delete remains available under `/api/documents`. Project RAG documents use the separate `/api/rag/projects/{project_id}/documents` lifecycle.
- FastAPI dependency injection (`src/backend/dependencies.py`) — shared session and conversation store dependencies for API routes.

## Security scanning added to CI
- **Bandit** static analysis runs on `src/` in CI, configured via `pyproject.toml` with known-issue skips.
- **Safety** checks dependencies for known vulnerabilities (continues on error — advisory only).
- **pip-audit** scans installed packages for known CVEs.
- `make security-scan` target added; `make ci` now includes `security-scan`.
- New optional dependency group `[security]` (`bandit>=1.7`, `safety>=3.0`, `pip-audit>=2.7`).

## Cleanup completed (stabilization phase)
- Reorganized repository support files: project plans under `docs/project/`, the generated OpenAPI schema under `docs/api/`, manual QA runners under `scripts/qa/`, and generated QA reports under ignored `artifacts/qa/`. Removed committed build metadata and stale generated reports.
- Removed the autonomous development supervisor, orchestrator state/transcripts, generated task logs, and related repository instructions. Development remains manual and CI continues to run through GitHub Actions.
- Removed the unused Dify API/Web services, their dedicated Redis service, reverse-proxy route, and environment wiring. Orion keeps its first-party chat routing and RAG service.
- Removed dead code: `main.py`, `dump_assessment.py`, `api_server.py` (duplicate of `cli.py`).
- Removed empty `__init__.py` files (PEP 420 namespace packages).
- Removed stale `docs/engineering/` legacy architecture docs.
- Removed Lovable branding: AGENTS.md, .lovable/, lovable-error-reporting, vite config dependency.
- Replaced `@lovable.dev/vite-tanstack-config` with direct standard plugin imports.
- Removed `--store` deprecated CLI flag.
- Removed debug `print()` statements from tool files.
- Removed unused Python imports.
- Updated README.md and HTML metadata.

## Phase 6 — Pipeline Architecture Hardening (delivery completed 2026-07-24; corrective behavior work open)

Full plan and per-task reconciliation: `docs/ai/10_PHASE6_PLAN.md`. All 32 task IDs across
9 work packages delivered their recorded artifacts in July 2026. In this section, ✅ means the
historical module/field/hook was delivered; it does **not** mean the current end-to-end behavior
passes the newer DR1 acceptance criteria.

Three rounds of evaluation testing (2026-07-24) identified 48 distinct issues. Root cause: CapabilityPlanner existed but was never wired into ExecutionEngine. **Fixed by ID 605.**

### WP6.1: Bug Fixes 🔴 (completed — 4 tasks)
- ID 601✅: System prompt overrides model identity to "Orion"
- ID 602✅: UnknownTargetError propagated instead of chat fallback
- ID 603✅: TargetResolver Step 4.5 detects nonexistent hostnames (non-alpha words)
- ID 604✅: Strong language enforcement in assessment + chat prompts

### WP6.2: CapabilityPlanner Integration 🟠 (completed — 4 tasks)
- ID 605✅: CapabilityPlanner wired into ExecutionEngine.execute() — filters capability_references
- ID 606✅: concepts.yaml expanded: hostname, kernel, uptime, load
- ID 607✅: capability_plans.yaml updated with evidence-level names
- ID 608✅: Operational names verified across CapabilityLibrary

### WP6.3: Parameter Extraction 🟠 (completed — 3 tasks) — `src/pipeline/parameter_extractor.py`
- ID 609✅: ParameterExtractor — service_name, port, process, path, time_range
- ID 610✅: Integrated into ExecutionEngine + InvestigationRequest.extracted_params
- ID 611✅: extracted_params threaded through ExecutionRuntime._execute_node()

### WP6.4: Answer Type Classification 🟠 (completed — 3 tasks) — `src/pipeline/answer_type.py`
- ID 612✅: AnswerType enum + AnswerTypeClassifier (FACT/LIST/TABLE/CHART/COMPARISON/ASSESSMENT)
- ID 613✅: Classification in ExecutionEngine, stored in InvestigationRequest.answer_type
- ID 614✅: Non-ASSESSMENT types attempt DeterministicResponder first in _assess()

### WP6.5: Tool Selection 🟡 (completed — 3 tasks) — `src/pipeline/tool_selector.py`
- ID 615✅: ToolSelector with ToolCategory enum (LINUX/GRAFANA/ZABBIX/INTERNET; the legacy KB enum value remains for compatibility but is never selected)
- ID 616✅: Integrated into ExecutionEngine via ToolSelector.select()
- ID 617✅: EvidencePackage.source_tool + EvidenceMerge tagging + ExecutionEngine._merge()

### WP6.6: DeterministicResponder Expansion 🟡 (completed — 5 tasks)
- ID 618-622✅: hostname, kernel version, top CPU, RAM available, load average responders

### WP6.7: Evidence Cache 🟡 (completed — 3 tasks) — `src/pipeline/evidence_cache.py`
- ID 623✅: EvidenceCache class (per-session, TTL 60s, thread-safe)
- ID 624✅: Integrated into ExecutionEngine (cache on success, put evidence)
- ID 625✅: EvidenceCache accepted in DeterministicAgent constructor

### WP6.8: Assessment Quality 🟡 (completed — 4 tasks)
- ID 626✅: AssessmentResult.severity field (ok/info/warning/critical)
- ID 627✅: ThresholdEvaluator — `src/pipeline/threshold_evaluator.py`
- ID 628✅: Prompt builder: stronger Vietnamese language enforcement
- ID 629✅: EvidenceCorrelation — `src/pipeline/evidence_correlation.py`

### WP6.9: Time Range & Visualization 🟢 (completed — 3 tasks)
- ID 630✅: TimeRangeResolver — `src/pipeline/time_range_resolver.py`
- ID 631✅: GrafanaTool.build_links() accepts time_range → adds from/to params
- ID 632✅: TimeRangeResolver wired into DeterministicAgent._build_tool_links()

### Current behavior reconciliation (DR1-006, 2026-08-05)

Source/test review confirms the Phase 6 artifacts above still exist, but it also confirms that
module existence and current behavioral acceptance are different states. The detailed 601–632
matrix and test evidence are in `docs/ai/10_PHASE6_PLAN.md`; the active corrective definitions
are in `docs/project/DETERMINISTIC_REASONING_BACKLOG.md`.

| Historical IDs | Artifact present | Current behavior gap / corrective owner |
|---|---|---|
| 601–604 | Identity/language prompts, separate unknown-target catch, hostname guard | DR1-306/309 completed target confidence + deterministic clarification; output validation remains DR1-703, DR1-706 |
| 605–608 | CapabilityPlanner/config/library wiring | DR1-301–309 completed canonical deterministic routing; DR1-401–405 now add pre-plan context and bounded multi-intent merging |
| 609–611 | Parameter parser plus runtime method plumbing | DR1-403/404 completed metadata-driven binding, required/type/pattern/range validation and safe bound-parameter traces |
| 612–617 | Answer-type/tool selectors and `source_tool` field | DR1-308 completed request/routing/evidence/strategy taxonomy; DR1-508/509 completed fact provenance and claim links; deterministic response filtering remains DR1-707 |
| 618–622 | Five responder methods | DR1-106 removed failure-to-zero/default-empty answers; DR1-501/502/505 completed canonical validity/completeness; DR1-601–609 now provide Findings and health aggregation; final response filtering remains DR1-707 |
| 623–625 | Per-session TTL cache and engine wiring | DR1-108 rejects failed/partial entries; DR1-507 completed params/timeframe/schema-aware keys, TTL classes and explicit stale policy |
| 626–629 | Severity field, threshold and correlation classes, prompt changes | DR1-601–605 completed canonical atomic/composite Findings and integrated them into assessment/trace; prompt/claim guards remain DR1-702–706 |
| 630–632 | Time parser and Grafana deep-link `from`/`to` wiring | DR1-406/407 completed temporal requirements/guards; DR1-503/509 completed Grafana fact normalization and provenance links; deterministic response filtering remains DR1-707 |

Therefore “Phase 6 delivery completed” is retained as history, while the named remaining owners
track unresolved behavior corrections. No open DR1 item is to be treated as proof that its predecessor module is
missing, and no historical ✅ is to be treated as proof that current QA acceptance passes.

## Not implemented (do not assume otherwise)
- **Multi-user accounts** — no login/password system, no user registration. Optional API key auth (`ORION_API_KEY`) exists for single-tenant protection.
- **Remote hosting** — no remote deployment yet. `docker-compose.yml` provides local HTTP; production TLS termination is not part of this stack.
- **Public production ingress/TLS** — the Nitro SSR UI is packaged for the local Docker stack, but public hosting, TLS termination, and multi-user hardening remain out of scope.

## Known issues / open items being tracked
- **SSH host key checking** is currently disabled by design for the local trusted-network use case — this is an intentional trade-off, recorded in `09_ARCHITECTURE_DECISIONS.md`, not an oversight.
- **Dependency reconciliation**: `pyproject.toml` dependencies have been partially reconciled. Third-party packages that are actually imported are declared; unused declarations (`numpy`, `requests`) remain as placeholders pending removal.
- **Frontend-backend session sync** (fixed 2026-07-23): Frontend ChatProvider now fetches sessions from `GET /api/sessions` on mount, creates sessions server-side via `POST /api/sessions`, and sends `session_id` with every `/api/query` request. Previously sessions existed only in local React state with generated IDs, causing the Orion Web session list to show zero sessions and sessions created in Orion Web to be invisible in the sidebar.
- **CLI session persistence** (fixed 2026-07-23): CLI `_run_agent()` now creates a `ConversationStore` with a UUID session ID (or resume ID) and passes it to `create_deterministic_agent()`. Previously `conversation_store=None`, so `DeterministicAgent._conversation_store` was `None` and `add_turn()` was never called.
- **Session metadata corruption** (fixed 2026-07-23): Four bugs compounded to corrupt session metadata when opening from the Web UI: (1) `_check_compress()` counted classifier messages (`[classified as ...]`) as real turns, causing premature summarization that cleared `_mem` entirely, (2) `ConversationStore._save()` never wrote `title` to disk, (3) `ConversationStore._load()` never restored `source` from disk (hardcoded `"api"`), (4) `chat-store.tsx` ignored server titles. Fixed: classifier messages excluded from turn counts, `title` saved/loaded, `source` restored from persisted data, frontend reads server titles.
- **Session splitting after server switch** (fixed 2026-07-24): `AppState.switch_server()` iterated over ALL sessions in `web_sessions` and assigned the last one to `agent.conversation_store`, causing conversations in an old session to be split across multiple session files. Root cause: the loop `for sid, cs in self.web_sessions.items()` assigned each session's store to the agent in arbitrary dict order, so the last session in the iteration "won". Fixed: `switch_server()` now preserves only the current `agent.conversation_store` before agent recreation, restoring it on the new agent instance.

## Phase 1 — Foundation (completed 2026-07-22)
- ID 87: Replaced broad `except Exception` in execution_runtime.py with specific exception types (`RuntimeError`, `ValueError`, `TypeError`, `OSError`, `CancelledError`).
- ID 88: Thread-safe database connection pool with semaphore-based concurrency (max 5, configurable via `ORION_DB_POOL_SIZE`). Connection reuse across requests instead of per-request creation.
- ID 89: Removed duplicate tool execution logic for infrastructure tools. RAG is no longer represented as a Chat child tool.
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
- ID 243: CI security scans run Bandit, Safety, and `pip-audit`; `pip-audit` uses its supported default non-zero exit behavior for discovered vulnerabilities.

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

## Historical evaluation findings (2026-07-24)

These findings drove the completed Phase 6 work. They are retained as history, not as the current defect list:
- **Identity leak** (🔴): System prompt does not override model identity → model self-identifies as Qwen/Alibaba
- **Language contamination** (🔴): Vietnamese queries may receive Chinese or English responses due to weak language enforcement
- **Target Resolution** (🔴): `TargetResolver` falls back to `localhost` when user types a nonexistent hostname (e.g. `serverabcxyz`). `UnknownTargetError` is caught and silently replaced by chat fallback, causing hallucination.
- **CapabilityPlanner not integrated** (🔴): Created in Phase 5 but not wired into `ExecutionEngine`. Pipeline still uses IntentResolver → EvidencePlanner exclusively, bypassing the Normalizer → CapabilityPlanner path.
- **Capability Routing gaps** (🟠): Intent keywords missing for "uptime", "hostname", "kernel", "load average", "database", "port", "zombie" → queries fall through to chat or wrong capability.
- **No parameter extraction** (🟠): Queries like "Service nginx" return all services instead of filtering to nginx.
- **No answer type differentiation** (🟠): All queries → assessment paragraph, even simple facts like "Hostname?" or "Zombie?".
- **No tool selection** (🟠): "sử dụng grafana" directive ignored; evidence from Linux/Grafana/Zabbix contaminated across sources.
- **Assessment quality** (🟡): Hallucinated risks (33% disk → "nguy cơ đầy"), no severity model, no threshold evaluation, no evidence correlation.
- **No evidence reuse** (🟡): Same evidence re-collected across turns; no per-session cache.
- **No time range support** (🟡): "CPU 1 giờ", "memory trend", "today" all return current snapshots.
- **No visualization pipeline** (🟡): "biểu đồ CPU" returns text assessment instead of Grafana embed.

Full analysis in `docs/ai/10_PHASE6_PLAN.md`.

## Next milestones
1. Phase 5 (Pipeline Architecture Upgrade) historical delivery is complete: Normalizer, CapabilityPlanner, and config-driven target resolution exist.
2. Phase 6 historical delivery is complete: 32/32 IDs across 9/9 WPs produced artifacts; current acceptance gaps are executed through the active DR1 backlog.
3. **GA1 general-agent and external-verification implementation is complete**: semantic routing, bounded Internet search/fetch, provenance, source constraints, action/content separation, revised QA sets, stage tests, ADR, and operator documentation are implemented. Query-search use still requires an operator-configured provider; direct URL fetch works independently within the Internet safety boundary.
4. **DR1 implementation is complete**: all 86 corrective task IDs now have recorded scope and
   verification evidence. Promotion remains gated by the release checklist, meaningful model/config
   baseline and CI artifacts; this is not a claim that a production deployment has occurred.
5. **Sprint 1 (`IMPLEMENTATION_BACKLOG.md`) is historical/complete**: items 001–012 implemented; item 013 evaluated and left HORIZON (2/5 gates met).
6. WP1 (`04_ROADMAP.md`) begins once public VM access is available — not before.

## Deterministic Reasoning v1 (DR1) — corrective backlog (implementation complete, 2026-08-07)
- **DR1-001 ✅ complete**: the active backlog is finalized as the single source of truth at `docs/project/DETERMINISTIC_REASONING_BACKLOG.md`. `BACKLOG.md` and `IMPLEMENTATION_BACKLOG.md` are explicitly historical/reference-only (see `docs/project/README.md`).
- **DR1-002 ✅ complete**: `ExecutionTrace` schema added (`src/pipeline/execution_trace.py`) — every pipeline request emits one trace with stage status/confidence, target, params, plan, evidence names, answer strategy, `llm_usage_reason`, `failure_stage`/`failure_reason` and safe serialization. `run_with_steps()` now returns `trace_id` + `execution_trace` (additive, backward-compatible).
- **DR1-003 ✅ complete**: the standalone HTTP QA runner `scripts/qa/orion_qa_runner.py` (stdlib-only, no `src/` import) is the accepted implementation with four TXT question suites under `tests/qa/cases/` (`cauhoi_kiemtra_v2`, `cauhoi_phanb`, `cauhoi_v4_adversarial`, `cauhoi_v5_workflow`). One run uses a single `session_id` across the suite, writes a transcript to `artifacts/qa/transcripts/` (or `--output`), and auto-starts/stops Orion via docker compose unless `--no-start` is used. The previous JSONL loader implementation (`scripts/qa/case_loader.py`, `--cases`, `tests/data/qa_cases/v5_multiline.jsonl`, `tests/qa/test_acceptance_parser.py`) was removed and the internal runners were reverted to their DR1-003-old hunks only.
- **DR1-004 ✅ complete**: transcript Q&A converted into a human-reviewed, stage-level golden dataset `tests/data/qa_cases/golden_core.yaml` — 39 cases covering groups A–J (+M), with expected concept/operation/intent/target/params/answer_type/routing_status/evidence_status/answer_strategy/`llm_usage_reason`/required_evidence per case plus `harness_error` flags to separate harness bugs from agent defects. `scripts/qa/build_golden.py` validates schema and coverage; `tests/qa/test_golden_schema.py` (35 tests) enforces group/tag coverage and forbids auto-generated ids.
- **DR1-005 ✅ complete**: the in-process baseline runner scores the golden suite by stage, records outcome rates/latency plus commit/config identity, and distinguishes behavioral mismatches from trace observability gaps with tri-state field status.
- **DR1-006 ✅ complete**: all historical Phase 6 IDs 601–632 were reconciled against current source/tests. `docs/ai/10_PHASE6_PLAN.md` now maps each delivered artifact to any open DR1 behavior correction; the Phase 6 section above explicitly separates delivery completion from current acceptance.
- **DR1-101 ✅ complete**: all execution backends now return immutable `CommandResult` with `CommandStatus`, exit code, separate stdout/stderr, error type, safe command/target metadata, duration, redacted serialization, and a temporary tuple-unpack compatibility adapter.
- **DR1-102 ✅ complete**: `LocalExecutionBackend` uses a stable C locale and preserves structured success/empty/non-zero/not-found/permission/timeout outcomes, including exit code and separate streams.
- **DR1-103 ✅ complete**: `SSHExecutionBackend` distinguishes a missing local ssh client, authentication failure, unreachable/DNS/network failure, connection timeout, remote command-not-found, permission denial, and other remote non-zero exits while retaining remote exit/stderr safely.
- **DR1-104 ✅ complete**: Child Tool dispatch now supports immutable `CapabilityResult`/`CapabilityStatus` (`VALID`, `VALID_EMPTY`, `PARTIAL`, collection/unsupported/parameter/parse failures), retains command results/warnings/fact names, and wraps legacy payload handlers without turning structured failures into success.
- **DR1-105 ✅ complete**: capability status, command results, warnings, produced-fact names, and collection failures now propagate through `ToolResult` and `EvidencePackage`; partial payloads remain inspectable but only `VALID`/`VALID_EMPTY` evidence satisfies requirements.
- **DR1-106 ✅ complete**: Linux command failures, including legacy tuple backends, can no longer become zero/empty/unknown measurements; core collectors omit unavailable facts, prompt summaries do not invent defaults, and deterministic responses require `VALID`/`VALID_EMPTY` evidence plus the specific fact needed for a claim.
- **DR1-107 ✅ complete**: capability failures now carry machine-readable code/category/recoverable metadata across capability, tool, and evidence boundaries; backend enum mappings distinguish transport/environment/command/parameter/parser/source-API/internal failures, and runtime result retries use only the structured recoverable flag.
- **DR1-108 ✅ complete**: EvidenceCache and both ExecutionEngine paths accept and reuse only `VALID`/`VALID_EMPTY` packages; failed/partial evidence never removes a runtime node or creates a negative cache hit, so a later request recollects after source recovery.
- **DR1-201 ✅ complete**: the API image installs the core Linux runtime binaries and exposes dependency readiness in `/api/health`; image build and in-container command smoke checks pass, while optional binary absence maps to `UNSUPPORTED` instead of fabricated values.
- **DR1-202 ✅ complete**: `localhost` explicitly means the Orion API runtime/container, displayed as `orion-api`; monitoring a physical host requires an explicit SSH target, and target identity is carried into Linux evidence and CLI output.
- **DR1-203 ✅ complete**: `TargetPreflight` fingerprints reachability, OS, init system, privilege, binaries, procfs/sysfs and caches by target/config hash with short TTL; a failed transport probe short-circuits dependent collection.
- **DR1-204 ✅ complete**: capability metadata now declares preconditions, all/any/optional binaries, init support, cost, reliability and produced facts; environment compatibility is validated before Child Tool dispatch from the single exported metadata source.
- **DR1-205 ✅ complete**: CPU utilization uses two `/proc/stat` snapshots with explicit percentage fields and `/proc/loadavg`/core metadata; locale-stable `top` remains only a bounded fallback.
- **DR1-206 ✅ complete**: service discovery/status uses a bounded systemd → SysV → OpenRC → process → port strategy, stops on transport/permission failures and marks indirect evidence partial with lower confidence.
- **DR1-207 ✅ complete**: service-log collection accepts validated service/time/limit parameters, queries an exact journal unit, permits only allowlisted file-log fallbacks and rejects shell-fragment injection.
- **DR1-208 ✅ complete**: network interfaces, statistics, routes and listening sockets have `/proc`/`/sys` fallbacks with explicit collection-source provenance and failure-safe semantics.
- **DR1-209 ✅ complete**: filesystem capacity, inode usage, cumulative disk I/O and device health are separate capabilities/facts; absent SMART/NVMe tooling is unsupported and capacity never implies physical health.
- **DR1-210 ✅ complete**: core Linux payloads use explicit bytes/seconds/percent schemas validated before `VALID`; the assessment prompt reads canonical unit-bearing keys rather than guessing aliases.
- **DR1-211 ✅ complete**: KnowledgeTool dispatch is fail-closed through a mandatory inspector chain with per-result receipts and trace counters; declared mutation risk/raw mutating parameters are blocked, and assessment remains tool-less/read-only.
- **DR1-301 ✅ complete**: investigation routing no longer invokes a Tier-2 model classifier; ambiguous/unsupported paths short-circuit deterministically and pipeline failures do not fall back to chat/model.
- **DR1-302 ✅ complete**: immutable `RequestFrame` is the canonical request contract across normalizer, intent, target and engine stages, with safe actual/expected frame trace serialization and a backward-compatible `semantic_request` alias.
- **DR1-303 ✅ complete**: deterministic normalization now handles accentless Vietnamese, reviewed code-switch aliases and bounded typo matching while preserving ranked match evidence and multiple explicit concepts.
- **DR1-304 ✅ complete**: standard-library semantic candidate retrieval combines exact, weighted token, character n-gram and edit signals; deterministic validation requires threshold, top margin and compatibility.
- **DR1-305 ✅ complete**: intent resolution exposes ranked candidates, score, enum confidence and ambiguity margin, validates concept/operation compatibility and prevents state words such as `down` becoming service names.
- **DR1-306 ✅ complete**: target resolution applies exact/scoped-alias/name-pattern precedence, fuzzy threshold + margin, alphabetic/numeric unknown-host guards and localhost fallback only when no explicit target exists.
- **DR1-307 ✅ complete**: target aliases have session/user/project/global scope and observed/suggested/approved/active/deprecated lifecycle; global activation requires reviewer/evidence metadata and transcript observations do not auto-promote.
- **DR1-308 ✅ complete**: request class, routing status, evidence status and answer strategy are first-class contracts on investigation/trace; the QA runner consumes them directly rather than deriving routing/evidence heuristically.
- **DR1-309 ✅ complete**: bounded deterministic templates clarify missing target/service/path/timeframe/concept/operation with at most three validated candidates before any model or evidence execution.
- **DR1-401 ✅ complete**: session investigation context stores only resolved semantic routing fields and persists separately from prompt summaries/raw evidence across JSON, SQLite and PostgreSQL stores.
- **DR1-402 ✅ complete**: structured context is applied before intent/target/capability planning; explicit targets override inherited targets, bounded follow-ups inherit only sufficiently supported target/concept/resource/time fields, and traces record the context stage.
- **DR1-403 ✅ complete**: `ParameterSpec`/`ParameterBinder` and route candidate metadata map service/process/path/port/ping/time values into child arguments; `nginx status` dispatches `get_service(name="nginx")`, and traces retain safe bound params.
- **DR1-404 ✅ complete**: graph parameters are validated before execution for required/default/type/enum/pattern/range and injection safety; missing or invalid values fail closed without reaching a child capability.
- **DR1-405 ✅ complete**: up to four explicit coordinated concepts become isolated subframes with shared semantics; evidence/capability plans merge deterministically, deduplicate, and retain graph parallelism, while over-broad requests clarify scope.
- **DR1-406 ✅ complete**: immutable timezone-aware `TimeRange` represents bounds, granularity, source phrase, temporal kind and comparison windows with injectable clocks; historical and future language creates series requirements rather than current snapshots.
- **DR1-407 ✅ complete**: temporal completeness requires two compatible comparison windows or at least six forecast points plus a defined growth model; incomplete requests return a deterministic insufficient-evidence response before assessment. Canonical fact-level completeness enrichment is now complete in DR1-505.
- **DR1-501/502/503 ✅ complete**: immutable canonical facts define explicit validity/freshness/provenance; Linux core and Zabbix/Grafana payloads normalize into consistent metrics, units, timestamps and source identities without failure-to-zero behavior.
- **DR1-504/505 ✅ complete**: per-investigation immutable `FactSet` provides deterministic indexes/merge order, and completeness matches required metric/target/parameters/timeframe/validity/freshness with explicit missing/failed/stale/contradictory reasons.
- **DR1-506 ✅ complete**: tolerance-aware reconciliation retains both sources and their provenance, marks conflicting facts `CONTRADICTORY`, and propagates contradictory evidence status instead of silently selecting a value.
- **DR1-507 ✅ complete**: cache identity includes target/capability/normalized parameters/timeframe/schema; TTL varies by fact class and stale reuse is opt-in with explicit stale facts.
- **DR1-508/509 ✅ complete**: evidence packages carry bounded raw data, canonical facts, failures and schema/source metadata; assessment consumes facts first, while safe provenance IDs and claim links redact secrets.
- **DR1-601–605 ✅ complete**: atomic thresholds now consume valid/fresh canonical facts (including derived per-core load); weighted composite rules preserve false/unknown/stale/failed semantics without implicit renormalization and emit immutable source-linked Findings into investigation, assessment and trace flows.
- **DR1-606–608 ✅ complete**: capability metadata declares reviewed recovery alternatives/error contracts; runtime recovery is loop-free and depth-two bounded with no transport-timeout expansion, while weighted missing-evidence selection and per-request round/capability/duration/cost budgets deterministically bound additional collection.
- **DR1-609/610 ✅ complete**: multi-source health aggregation prioritizes active incidents and evidence gaps before warnings/healthy facts per target and globally; versioned Pydantic-validated YAML rules require owner/rationale/source cases and explicit approval, with no production auto-learning path.
- **DR1-801–811 ✅ complete**: contract/routing/context/fact/reasoning/transcript/security regression suites, offline stage/budget dashboard and CI `acceptance-gates` now make P0 accuracy and safety regressions deterministic and artifact-backed.
- **DR1-901–905 ✅ complete**: execution/tool contracts and operator guides now document structured results, Facts/Findings, provenance, bounded recovery, exact collection failure codes, and localhost/container semantics; ADR-0008/0009 establish evidence validity and deterministic reasoning v1. `docs/migrations/deterministic_reasoning_v1.md` records the adapter/removal plan, while strict temporary feature flags support independent rollout/rollback of structured command provenance, canonical Facts, composite rules, and claim grounding without changing response schemas.
- **DR1-906/907 ✅ complete**: PR1–PR9 rollout order, phase exit criteria and compatibility rollback rules are fixed in the active backlog/migration plan. `CHANGELOG.md` now provides the release checklist: retain CI acceptance artifacts and a meaningful (non-smoke) model/config baseline before a release decision. All 86 DR1 tasks are complete; the checklist intentionally keeps production promotion as a separately evidenced release action.

> **Last updated:** 2026-08-07 (all 86 DR1 tasks complete; DR1-906/907 rollout and release-verification controls added. A production release remains gated, not implied.)

## Task 013: Plugin/Extension System — HORIZON Gate Evaluation (2026-07-26)

Task 013 remains **HORIZON** (not promoted to active backlog). Gate evaluation:

| Gate | Requirement | Status |
|------|-------------|--------|
| 1 | Community demand for ≥3 monitoring platform integrations | ❌ Not met |
| 2 | Security Pipeline (Task #004) complete and proven | ✅ Complete |
| 3 | Tool Auto-Discovery (Task #005) complete and proven | ✅ Complete |
| 4 | Plugin API design reviewed | ❌ Not met |
| 5 | API stability commitment made | ❌ Not met |

**Result:** 2/5 gates met. Implementation deferred until all 5 gates are satisfied. No code changes. Task #005 (Tool Auto-Discovery) already achieves 80% of the plugin system's value (reducing tool registration from 4 steps to 1) at 20% of the cost. The `ToolRegistry` in `src/tool/registry.py` provides auto-discovery of `Tool` subclasses with `_CAPABILITIES`. The `InspectorChain` in `src/pipeline/security/` enforces read-only execution for all tool dispatch paths. These two components together satisfy the architectural goals the plugin system was intended to address.


## Post-Phase 6 improvements (2026-07-24)

Based on structured evaluation of a 60-turn conversation with Orion, the following improvements were implemented to address the 6 key weaknesses identified:

### Round 1 fixes (conversation evaluation)

### DeterministicResponder expansion
- **Service-specific responses**: `_check_service_status()` now accepts `service_name` parameter to return status for a specific service (nginx, docker, sshd, etc.) instead of generic "all 69 services running".
- **Swap**: New `_check_swap()` method extracts swap usage from Memory evidence.
- **Uptime**: New `_check_uptime()` method extracts uptime from CPU/System evidence.
- **Listening ports**: New `_check_listening_ports()` method extracts open ports from Network evidence.
- **Disk full**: New `_check_disk_full()` method checks filesystem usage and flags near-capacity (>80%) mounts.
- Expanded keyword detection for Vietnamese queries (uptime, swap, port listen, disk full).

### ThresholdEvaluator hardening
- Added swap thresholds: >50% warning, >80% critical.
- Added `memory_usage_pct`, `load_5min`, `failed_services_count`, `failed_count` thresholds.
- Documented risk calibration: >90% critical, >80% warning, <=80% ok.

### ParameterExtractor improvements
- Expanded `_SERVICE_NAMES` regex to include `grafana-server`, `zabbix-agent`, `zabbix-server`, `prometheus`, `node_exporter`, `containerd`, `openvpn`, `bind9`.
- Added "trạng thái X" / "kiểm tra X" Vietnamese pattern matching for service extraction.

### Config improvements
- `config/concepts.yaml`: Added Vietnamese synonyms for swap (bộ nhớ ảo, phân vùng trao đổi), RAM (ram còn trống, ram available, ram free).
- `config/capability_plans.yaml`: Added `CPU` to memory/diagnose plan for richer context.

### Round 2 fixes (conversation evaluation, 2026-07-24)
7 improvements implemented based on structured Q&A evaluation of 14 Orion responses:

1. **Vague health-check routing** (`src/agent/deterministic_agent.py`): Added `_is_vague_health_check()` with 18 patterns (VI + EN). Questions like "có vấn đề gì không?", "có ổn không?" now route to pipeline → `assess_machine()` instead of chat fallback.

2. **Swap info always collected** (`src/tool/linux/capabilities/memory.py`): `_get_memory()` now parses SwapTotal/SwapFree from `/proc/meminfo` inline, returning `swap_total_kb`, `swap_used_kb`, `swap_free_kb`, `swap_usage_percent`. Eliminates 100% of "không có thông tin swap" responses.

3. **Top memory consumers always collected** (`src/tool/linux/capabilities/memory.py`): `_get_memory()` now runs `ps aux --sort=-%mem --no-headers` and returns top 6 consumers with user, pid, cpu_pct, mem_pct, command.

4. **Bad target cache** (`src/pipeline/target_resolver.py`): Per-session `_bad_targets` set prevents retrying the same failed target across multiple turns. Previously `server01`/`srv01`/`sv01` would each trigger a full resolution attempt → same `UnknownTargetError`. Now cached after first failure.

5. **Chat system prompt depth** (`src/agent/deterministic_agent.py`): Chat prompt now instructs: "provide a detailed technical explanation (3-5 sentences minimum) with examples where helpful" for technical concepts. Also: "ask for missing details before writing" when user requests templates.

6. **Language enforcement** (`src/agent/deterministic_agent.py`): Stronger chat prompt: "QUAN TRỌNG: Bạn PHẢI trả lời TOÀN BỘ bằng tiếng Việt. Không được trả lời bằng bất kỳ ngôn ngữ nào khác." (already present — verified working; assessment prompt already has similar enforcement at line 319-323 of prompt_builder_v2.py).

7. **Disk threshold hallucination** (`src/pipeline/threshold_evaluator.py`): Verified existing thresholds: `usage_percent > 80%` = warning, `> 90%` = critical. Issue was LLM hallucination ("34% → nguy cơ đầy"), not missing threshold. ThresholdEvaluator (ID 627) + EvidenceCorrelation (ID 629) already address this in assessment prompt.
