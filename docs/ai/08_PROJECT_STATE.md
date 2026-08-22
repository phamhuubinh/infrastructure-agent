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

- `orion run`: interactive bounded-controller chat with deterministic
  validation/execution boundaries and SQLite conversation persistence.
- `python3 -m src.cli web`: source FastAPI + Vite Web runtime.
- Installed `orion web` / `orion log`: Docker service control and log viewing.
- CLI target commands: add, list, and remove JSON-backed local/SSH targets;
  concrete aliases from the runtime SSH configuration are also listed as
  non-persistent SSH targets.
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

- RuntimeFactory-built configured CLI/Web agents use
  `AgentControllerLoopCoordinator` and `ControllerAdapter` as the primary
  natural-language path. **Model owns reasoning and next-action selection.
  Harness owns authority, execution, evidence and completion.**
- The controller receives the current request, narrow hard constraints, bounded
  validated session context, and fixed small first-turn capability categories;
  it does not receive the complete capability registry/schema set. It returns
  exactly `FINAL`, `DISCOVER`, `ACTION`, `CLARIFY`, or `REFUSE`.
- Sensitive disclosure and mutation hard stops are built before controller
  execution and can finish before model, action, or tool calls. Definitional
  questions about credential concepts remain answerable.
- `DISCOVER` reveals only a requested approved category as bounded summaries;
  no capability executes. For an `ACTION`, selected capability detail and typed
  schema are disclosed only when required, before typed arguments are supplied.
  That schema handshake is not execution.
- `AgentActionValidator` owns deterministic registered-capability, typed
  parameter, exact target/source, availability, read-only/safety, and budget
  validation. Invalid actions return compact control feedback; the harness does
  not semantically repair or retry them automatically.
- `AgentActionExecutor` executes at most one validated action per turn. Linux,
  Grafana, and Zabbix actions retain existing `KnowledgeTool`/Child Tool
  boundaries; verified Internet actions use
  `ExternalVerificationExecutor`/`InternetTool`; the calculator is first-class
  `compute.deterministic`, not a Child Tool. The model has no arbitrary shell
  or HTTP authority.
- Results become compact bounded observations with safe identity,
  facts/provenance where applicable, and control codes. The controller may then
  choose another bounded decision. Controller/model/action/tool/discovery/input
  and completion limits bound the loop; completion checks can return control
  feedback for another bounded round.
- A deterministic final boundary, response sanitizer, and response budget
  deliver exactly one final public response. The configured v2 path preserves
  CLI/API/session/artifact contracts.
- `/api/query` exposes the existing credential-safe `trace_id` and
  `execution_trace` alongside `steps`. The trace projector bounds size/depth
  and excludes controller prompts, raw Agent v2 request, raw action arguments,
  raw evidence/command output, credentials, and hidden reasoning.
- `SemanticPlannerAdapter`, `SemanticPlan`, and `SemanticPlanBinder` remain in
  setup-mode, compatibility, and historical source paths only; they are not
  the configured RuntimeFactory primary architecture.

## Evidence and reasoning

- `KnowledgeTool` is the only execution entry point to registered Child Tools.
- `CommandResult`, `CapabilityResult`, `ToolResult`, and `EvidencePackage`
  preserve typed outcomes, separate streams, structured failure metadata,
  provenance, and bounded serialization.
- Assessment-model evidence has a deterministic global byte/item budget.
  Canonical facts, status, missing markers, contradictions, source/target
  identity, and compact provenance take priority. Raw payload is allowed only
  when an assessment request explicitly requires a valid fact-less package,
  under a separate redacted budget.
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
- A controller-provided `FINAL` answer is accepted only after `CompletionCheck`
  evaluates hard constraints and compact observations for refusal/read-only,
  target/source/URL identity, current evidence, calculator consistency, action
  claims, and evidence sufficiency. `CompletionCheck` uses
  `FinalResponseGuard` only for the calculator exact-value invariant. A rejected
  FINAL becomes compact deterministic control feedback for another bounded
  controller round; an accepted FINAL becomes the terminal controller result.
- Accepted Agent v2 FINALs then use the existing artifact/config validation
  when applicable, universal output sanitizer, response budget, and API-safe
  trace/public projection before exactly one public response is delivered.
- `SemanticRelevanceVerifier` and `SemanticResponseRepairer` remain legacy
  semantic-loop finalization components. They are not automatically constructed
  or invoked for the configured controller path.
- Provider usage is normalized into `ModelCallUsage`, separating provider/model,
  purpose, latency, input tokens, reasoning tokens, visible-output tokens,
  total-output tokens, configured effort, and the separate
  `estimated_input_tokens` estimate. Unknown provider fields stay `null` —
  never zero — and hidden reasoning text is never stored.
- `ModelUsageRecorder` exposes per-purpose aggregates and at most 16 per-call
  entries under `runtime_metrics.model_usage`. Aggregate token fields use strict
  unknown propagation rather than partial sums; excess entries are counted in
  `dropped_calls`.

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

- Orion can start with an empty model registry. RuntimeFactory then installs
  both `UnconfiguredAssessmentAdapter` and `UnconfiguredPlannerProvider`, so
  model-dependent semantic requests return a clear setup-mode response instead
  of falling back to guessed lexical live routing. Deterministic hard-safety,
  health, and model-management paths remain operational.
- With a configured model, RuntimeFactory builds a session-local
  `ControllerAdapter` from the same selected assessment adapter or ordered
  fallback chain. OpenAI-compatible adapters reuse their existing `LLMClient`;
  test/other adapters use the narrow raw-assessment bridge. No credentials are
  copied into controller prompts or traces, and provider clients hold no mutable
  conversation state.
- Provider-neutral controller contracts use strict structured decisions,
  bounded prompt context, compact discovery summaries, selected-capability
  detail/schema disclosure, typed pre-execution validation, and compact
  deterministic observations. Provider failure and malformed output fail
  closed; neither path exposes execution authority.
- The first controller input is budgeted and includes only bounded
  request/context/decision fields plus small categories. Relevant validated
  target/concept/service/path/time/source/exclusion/clarification fields may be
  included; raw evidence receipts are not controller context.
- `AgentControllerLoopCoordinator` is the primary RuntimeFactory request loop.
  The controller may choose the next approved action after observations, but
  validation, execution, recovery, evidence, budgets, and completion remain
  harness-owned. Provider, validation, execution, response, budget, and
  state-limit failures terminate safely.
- `SemanticRelevanceVerifier` and `SemanticResponseRepairer` remain available on
  the legacy semantic-loop path, where relevance and the bounded repair cycle
  operate under that path's existing finalization contract. They are not part
  of the configured Agent v2 controller finalization path.
- `compute.deterministic` accepts reviewed typed arithmetic arguments and runs
  the calculator once without Child Tool access. Supported arithmetic includes
  binary operations, average, percent-of, worker/task rate, and rate-unit
  conversion; invalid or ambiguous contracts fail explicitly.
- Current external information and explicit public URLs execute through the
  bounded external verifier. Verified evidence/provenance is assessed;
  unavailable search/fetch returns an explicit unverified response and never
  falls back to stale model memory.
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
- Controller context selection inherits only previously validated relevant
  target/concept/service/path/time/source/clarification fields for a follow-up;
  unrelated new requests receive no inherited controller context and do not erase
  stored infrastructure state. An explicit target switch clears task-scoped
  concepts, resources, and source filters before applying the new request;
  explicit sources/exclusions replace stale filters. Evidence receipts are
  never included in controller context. Raw history/evidence never becomes
  action authority.
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
  constraints default to enabled. The general-agent routing flag is retained
  for compatibility; RuntimeFactory uses the Agent v2 controller as the
  primary natural-language path.
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
