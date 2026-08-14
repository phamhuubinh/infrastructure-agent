# 08 - Project State

> Concise inventory of the current repository. Source code, configuration,
> schemas, and tests take precedence if this summary drifts.

## Runtime scope

Orion is a local, single-operator application with CLI, Web UI, FastAPI API,
Docker Compose packaging, and an Electron wrapper. The Docker entry point is
loopback HTTP through Nginx. Source mode uses SQLite; Docker Compose uses its
bundled PostgreSQL service. API-key middleware supplies single-tenant API
protection.

## Application surfaces

- `orion run`: interactive deterministic chat with SQLite conversation
  persistence.
- `python3 -m src.cli web`: source FastAPI + Vite Web runtime.
- Installed `orion web` / `orion log`: Docker service control and log viewing.
- CLI target commands: add, list, and remove JSON-backed local/SSH targets.
- CLI/Web model settings: save, test, select, list, and delete user-managed
  model connections.
- Web Chat: isolated sessions, regeneration, response timing, evidence steps,
  trace details, and model selection.
- Web document analysis: isolated RAG projects, upload/delete, retrieval, model
  synthesis, and bounded analysis history.
- Generic document API: upload/list/get/download/delete outside the project RAG
  lifecycle.
- Electron desktop: packaged UI/proxy for a running local Docker installation.

## Routing and execution

- `RequestFrame` and deterministic semantics distinguish stable knowledge,
  content generation, live infrastructure inspection, current external
  information, explicit URLs, source constraints, and mutation intent.
- Stable/general and generation requests do not collect infrastructure
  evidence. Mutations are refused.
- Current/online and explicit-URL requests use bounded deterministic Internet
  verification; unavailable verification remains unverified/unknown.
- Infrastructure requests resolve explicit targets before planning. Unknown or
  ambiguous explicit targets clarify without `localhost` fallback.
- Exact Grafana/Zabbix/SSH/Internet source constraints and exclusions are
  enforced before capability execution.
- Metadata-driven parameter binding validates required fields, types, patterns,
  ranges, and unsafe values before dispatch.
- Coordinated requests use bounded decomposition and a deduplicated capability
  graph.
- Canonical `TimeRange` and `TemporalEvidenceGuard` enforce compatible windows
  for comparison and sufficient series/growth-model evidence for forecast.
- Every request exposes a credential-safe `trace_id` and `execution_trace` in
  `/api/query`, alongside the existing `steps` array.

## Evidence and reasoning

- `KnowledgeTool` is the only execution entry point to registered Child Tools.
- `CommandResult`, `CapabilityResult`, `ToolResult`, and `EvidencePackage`
  preserve typed outcomes, separate streams, structured failure metadata,
  provenance, and bounded serialization.
- Only fresh `VALID`/`VALID_EMPTY` evidence satisfies requirements or enters
  cache reuse.
- Fact normalizers cover Linux, Grafana, and Zabbix evidence. Reconciliation
  preserves contradictions.
- Reviewed atomic rules are loaded from `config/rules/`; startup fails when the
  required reviewed rule set is absent.
- Composite rules, Findings, health aggregation, bounded recovery, and one
  bounded evidence-expansion round are implemented behind current runtime
  controls.
- `DeterministicResponder` handles supported simple answers before model
  assessment.
- The action-claim guard is mandatory. Hidden-reasoning removal, language
  cleanup, and a non-empty fallback apply at the final API boundary.
  Evidence-grounding and numeric claim guards apply when `claim_guard` is
  enabled.

## Child Tools

- `LinuxTool`: local/SSH evidence, target preflight, service strategy,
  process/log/network/filesystem/inode/I/O/device-health collectors, and
  structured command failure semantics.
- `GrafanaTool`: dashboards, data sources, alerts, annotations, and time-range
  links through the configured API.
- `ZabbixTool`: hosts, item/history data, triggers, events, templates, and
  maintenance information through the configured API.
- `InternetTool`: provider-neutral search and public-URL fetch with SSRF,
  redirect, DNS, timeout, and response-size controls.

RAG is intentionally absent from chat tool registration.

## Models

- Orion starts with an empty model registry and an explicit unconfigured
  assessment adapter.
- Provider-neutral semantic-planning contracts cover a strict versioned
  `SemanticPlan` wire shape, bounded prompt context, structured provider
  failures/clarifications, compact capability summaries, single-capability
  detail expansion, and typed pre-execution validation results. These
  contracts do not participate in the current deterministic chat runtime.
- User-managed model endpoints are stored and health-tested by
  `ModelConfigStore`.
- Chat can use registered OpenAI-compatible and Anthropic provider adapters
  with an ordered fallback chain. CLI/Web connection forms expose
  OpenAI-compatible, Ollama, and vLLM choices.
- RAG analysis requires the active OpenAI-compatible model connection; project
  and upload operations remain available without one.
- Orion does not install or manage model runtimes or weights.

## Sessions and persistence

- CLI and source Web sessions use `~/.orion/sessions.db`.
- Docker sessions use PostgreSQL through `ORION_DATABASE_URL`.
- Each Web session has its own Agent, conversation store, evidence cache,
  semantic investigation context, and execution lock.
- Session context persists only bounded target/concept/service/path/time,
  source constraints, incident IDs, pending clarification, answer shape,
  evidence receipts, and prior evidence status; raw tool observations are not
  conversation memory.
- Semantic-planner context selection inherits only relevant
  target/concept/service/path/time/source/clarification fields for a follow-up;
  unrelated new requests clear that planner context and evidence receipts are
  never included in it.
- RAG project metadata, document data, vector collections, BM25 indexes, and
  the latest 100 analyses persist under `RAG_DATA_DIR` in the RAG volume.

## Deployment and security

- `install.sh` creates runtime secrets, prepares the external monitoring
  credential file when absent, builds/starts the Compose stack, installs the
  host launcher, and optionally records an existing model connection.
- `uninstall.sh` removes Orion containers, images, volumes, sessions, RAG data,
  model registry, logs, runtime secrets, and launcher while preserving the
  source checkout and independently managed model runtimes. Non-interactive
  uninstall preserves `/etc/orion/tool-credentials.json`.
- Tracked `tools.json` contains registry metadata only. Packaged Grafana and
  Zabbix endpoints/tokens come from `/etc/orion/tool-credentials.json`, mounted
  read-only.
- SSH host-key verification defaults to enabled. Per-target disabling is an
  explicit trusted-network exception.
- Internet fetch/search validates public addresses and every redirect, pins the
  validated address for the connection, and redacts credential-bearing
  provenance.
- Docker binds browser/API ports to loopback; PostgreSQL, SSR UI, and RAG are
  internal services.

## Configuration defaults

- The optional feature-flag file is absent in the repository; schema defaults
  apply unless `ORION_FEATURE_FLAGS_FILE` or per-flag environment overrides are
  provided.
- General-agent routing, external verification, web search, and source
  constraints default to enabled.
- Structured command exposure, canonical Fact exposure, composite rules, and
  model claim grounding default to disabled. Mandatory action safety remains
  enabled independently.

## Verification assets

- Python unit/contract suites cover agent, pipeline, tools, model, backend,
  security, CLI, benchmark helpers, and QA schemas.
- The independent RAG service has its own locked test environment.
- UI uses TypeScript, ESLint, Vitest, and client/SSR builds.
- Desktop has Node tests for its Docker/API proxy contract and Electron package
  configuration.
- GitHub Actions defines Python-version tests, type checking, RAG tests, UI
  checks/build, Desktop checks/package, security scans, image builds, Compose
  smoke checks, and acceptance gates.
- Manual QA runners write ignored artifacts under `artifacts/qa/`.
