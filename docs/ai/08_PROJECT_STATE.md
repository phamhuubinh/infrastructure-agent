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

- `orion run`: interactive semantic-planner chat with deterministic
  validation/execution boundaries and SQLite conversation persistence.
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

- RuntimeFactory-built CLI/Web agents use `SemanticPlannerAdapter` as the
  primary natural-language semantic interpreter. The planner emits a strict
  typed `SemanticPlan`; legacy lexical routing remains only as a compatibility
  path for explicitly constructed agents without a planner.
- The first planner prompt contains the request plus bounded relevant session
  context and schema only. It contains no commands, credentials, tool schemas,
  capability details, evidence, or hidden reasoning.
- `SemanticPlanHarnessValidator` owns hard mutation/read-only checks,
  registry-backed target validation, exact source constraints/exclusions,
  freshness normalization, compute validation, and multi-intent structure.
  Planner failure or invalid output fails closed and does not revive lexical
  live routing.
- Stable/general and generation plans do not collect infrastructure evidence.
  Deterministic compute uses the reviewed calculator. Capability-assisted
  plans must bind successfully before any collector can run.
- Sensitive disclosure requests (hidden instructions, credentials,
  credential files) are refused before semantic planning or direct-response
  generation; their traces omit the raw request and normalized frame.
  Definitional questions about credential concepts remain answerable.
- Current/online and explicit-URL plans use bounded deterministic Internet
  verification; unavailable verification remains unverified/unknown and never
  falls back to stale model memory.
- `SemanticPlanBinder` maps validated capability-assisted plans onto the
  existing evidence planner, capability resolver/router, parameter binder, and
  canonical `RequestFrame`. Unknown/ambiguous targets and unavailable exact
  sources fail closed rather than silently falling back.
- Multi-intent plans contain 2-4 non-recursive child subplans. Dependencies may
  point only to earlier children; child execution is isolated and prerequisite
  results are passed only through explicit dependencies. One parent response is
  produced.
- Canonical `TimeRange` and `TemporalEvidenceGuard` enforce compatible windows
  for comparison and sufficient series/growth-model evidence for forecast.
- `SemanticLoopCoordinator` runs the finite states `PLAN`, `VALIDATE`,
  `EXECUTE`, `ASSESS/RESPOND`, and `DONE`/`FAIL` with a default maximum of six
  state transitions. There is no planner-controlled retry loop; configured
  planner provider failover is bounded to one call per provider.
- Every request exposes a credential-safe `trace_id` and `execution_trace` in
  `/api/query`, alongside the existing `steps` array. The API trace projector
  bounds size/depth and removes/redacts prompt, credential, raw-output, and
  hidden-reasoning fields while preserving safe planner/validation/usage
  metadata.

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
- Semantic-loop responses pass deterministic postcondition checks for validated
  target identity, current-data verification, the read-only boundary, exact
  calculator output, represented language/shape constraints, and actually used
  provenance. A failed check first creates a safe deterministic replacement and
  bounded violation metadata.
- A planner-provided `final_answer` remains untrusted model prose: it passes
  deterministic sensitive-request refusal, the same final postconditions and
  relevance verification as other model drafts, and at most one repair before
  release. Eligible benign direct answers still avoid a second response-model
  generation call.
- If hard postconditions pass and the draft is model-generated, one compact
  `SemanticRelevanceVerifier` call checks request/answer alignment. It sees only
  the original request, an allowlisted plan summary, and a bounded draft; it
  returns only `aligned`/`not_aligned` plus a stable reason code.
- When final postconditions are not satisfied and the response was
  model-generated, `SemanticResponseRepairer` gets at most one bounded repair
  attempt. The repaired candidate re-enters the same deterministic verification
  once with repair disabled. A second failure, unavailable repair, or empty
  repair leaves the safe deterministic replacement. Traces record only bounded
  repair status/reason metadata.
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
  `SemanticPlannerAdapter` from the same selected assessment adapter or ordered
  fallback chain. OpenAI-compatible adapters reuse their existing `LLMClient`;
  test/other adapters use the narrow raw-assessment bridge. No credentials are
  copied into planner prompts or traces, and provider clients hold no mutable
  conversation state.
- Provider-neutral semantic-planning contracts cover the strict versioned
  `SemanticPlan` wire shape, bounded prompt context, structured provider
  failures/clarifications, compact capability summaries, single-capability
  detail expansion, and typed pre-execution validation results.
- OpenAI-compatible planner calls send the canonical JSON Schema through
  native structured output when the configured endpoint supports it. Endpoints
  without that capability use only the compact wire hint and the same strict,
  fail-closed parser; neither path exposes execution authority.
- The first-pass planner prompt is under the SIMPLE input-context budget and
  contains only the bounded request/context/schema contract. Session context
  can include relevant target/concept/service/path/time/source/exclusion and
  pending-clarification fields; evidence receipts are not planner context.
- `CapabilitySummaryIndex` and `LazyCapabilityDetailExpander` implement compact
  post-selection disclosure contracts, but the first-pass planner receives no
  capability index. The current `SemanticPlanBinder` binds validated semantics
  through the existing evidence planner/capability resolver/parameter binder
  without returning raw capability detail or command authority to the model.
- `SemanticPlanHarnessValidator` validates mutation intent, registry-backed
  target references, exact source constraints/exclusions, freshness, compute,
  and bounded multi-intent structure before binding. A planner-provided final
  answer is eligible only for conservative stable/general cases that do not
  require tools, current data, calculation, clarification, target resolution,
  or URL verification.
- `SemanticLoopCoordinator` is the primary RuntimeFactory request loop. Direct
  answers skip binding/execution; structured compute runs the reviewed
  calculator once; capability-assisted plans dispatch through the environment
  engine or external verifier after validation/binding; multi-intent uses
  isolated validated child runs. Provider, validation, binding, execution,
  response, budget, and state-limit failures terminate without planner-
  controlled retries.
- `SemanticRelevanceVerifier` and `SemanticResponseRepairer` are created with a
  planner-configured Agent. Relevance is checked only for model-used responses
  that pass the hard guard; at most one repair attempt can follow a failed
  final verification, and the repair is verified once more.
- A semantic plan may include a structured `CalculatorRequest` with typed,
  operation-specific operands and units. The harness validates it and the loop
  runs the reviewed deterministic calculator once without tool access.
  Supported arithmetic includes binary operations, average, percent-of,
  worker/task rate, and rate-unit conversion; invalid or ambiguous contracts
  fail explicitly.
- Supplied-text arithmetic recognizes reviewed VI/EN forms and excludes
  machine/worker count nouns (e.g. "3 máy") from average operands.
- Capability-assisted semantic plans for current external information and
  explicit public URLs execute through the bounded external verifier. Verified
  evidence/provenance is assessed; unavailable search/fetch returns an explicit
  unverified response and never falls back to stale model memory.
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
  unrelated new requests receive no inherited planner context and do not erase
  stored infrastructure state. An explicit target switch clears task-scoped
  concepts, resources, and source filters before applying the new request;
  explicit sources/exclusions replace stale filters. Evidence receipts are
  never included in planner context.
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
  for compatibility; RuntimeFactory still uses semantic planning as the
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
