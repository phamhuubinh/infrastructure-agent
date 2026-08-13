# 09 - Architecture Decisions

This file summarizes decisions enforced by the current implementation. Detailed
records live under `docs/adr/`.

## AD-001 — Deterministic before AI

**Decision:** Deterministic code owns request semantics, target/source
resolution, evidence selection, execution, recovery, thresholds, and safety.

**Consequence:** Model output cannot select a tool, command, target, retry, or
recovery path.

## AD-002 — The model assesses bounded evidence

**Decision:** The assessment model interprets evidence and writes the final
explanation when a deterministic response is not sufficient.

**Consequence:** The model sees bounded prompt/evidence contracts and never
receives infrastructure authority.

> Detailed record: `docs/adr/ADR-0002-llm-assessment-only.md`

## AD-003 — KnowledgeTool is the single collection entry point

**Decision:** `ExecutionRuntime` reaches Child Tools only through
`KnowledgeTool`.

**Consequence:** Capability routing and inspectors apply consistently, and the
pipeline does not depend on domain implementations.

> Detailed record: `docs/adr/ADR-0003-knowledge-tool-single-entry-point.md`

## AD-004 — One Child Tool owns one domain

**Decision:** The chat domains are Linux, Grafana, Zabbix, and Internet.

**Consequence:** Each domain owns its capability metadata and reviewed
collection strategy. Project RAG remains outside chat registration.

## AD-005 — Child Tool metadata is canonical

**Decision:** Capability definitions belong to Child Tools. `KnowledgeTool`
aggregates them and the execution pipeline consumes the aggregation.

**Consequence:** Capability names, parameters, produced Facts, prerequisites,
cost, reliability, alternatives, and mutation risk are not duplicated in
pipeline modules.

## AD-006 — Live infrastructure is the operational source of truth

**Decision:** Fresh valid observations outrank cached or model-known data.

**Consequence:** Cache reuse requires valid fresh evidence and never hides a
collection failure, contradiction, or stale result.

## AD-007 — Execution state is ephemeral

**Decision:** Commands, raw observations, DAG state, and runtime context exist
only for the investigation that produced them.

**Consequence:** Execution behavior does not depend on hidden operational state
from earlier requests.

> Detailed record: `docs/adr/ADR-0004-stateless-state-management.md`

## AD-008 — Conversation persistence is bounded

**Decision:** Session stores persist user/assistant turns, compressed summaries,
and the typed `SessionInvestigationContext`; they do not persist raw tool
outputs or execution state as conversation memory.

**Consequence:** Follow-ups can inherit supported semantic fields without
turning an old infrastructure observation into current evidence.

## AD-009 — Evidence quality outranks prompt complexity

**Decision:** Improve Tool -> Evidence -> Assessment in that order.

**Consequence:** Missing evidence remains explicit instead of being compensated
for with longer prompts or additional model loops.

## AD-010 — Composite operational capabilities are preferred

**Decision:** Expose bounded operational capabilities instead of requiring
model-mediated chains of atomic calls.

**Consequence:** The execution DAG can batch independent work and reduce model
interaction.

## AD-011 — Dependencies remain one-directional

**Decision:** The infrastructure path follows
`Agent -> ExecutionEngine -> KnowledgeTool -> Child Tool -> Environment`.

**Consequence:** Reverse dependencies and direct pipeline-to-domain imports are
prohibited.

## AD-012 — Architecture changes require human approval

**Decision:** Repository work preserves documented ownership and boundaries
unless the user explicitly approves an architecture change.

**Consequence:** Architecture does not change implicitly during feature or bug
work.

## AD-013 — Repository state overrides stale documentation

**Decision:** Current code, configuration, schemas, and tests are the primary
implementation evidence.

**Consequence:** Documentation is corrected when it disagrees with verifiable
repository behavior.

## AD-014 — SSH host-key verification defaults to enabled

**Decision:** SSH uses `StrictHostKeyChecking=yes` and the Orion runtime user's
known-hosts file by default. A target can explicitly disable the check.

**Consequence:** Operators verify and register host keys. A per-target disabled
check is a deliberate trusted-network exception with weaker transport
authentication.

## AD-015 — Secrets remain outside source and tracked registry metadata

**Decision:** Credentials and deployment endpoints are not hardcoded or stored
in tracked `tools.json`.

**Consequence:** Packaged Grafana/Zabbix credentials come from
`/etc/orion/tool-credentials.json`, mounted read-only. Logs, traces, command
serialization, and provenance apply credential redaction.

## AD-016 — The supported deployment is local and single-operator

**Decision:** Source mode and Docker Compose expose local runtimes. API-key
middleware protects a single tenant.

**Consequence:** Compose binds browser/API ports to loopback and keeps database,
SSR UI, and RAG services internal.

## AD-017 — DeterministicAgent orchestrates; it does not grant model authority

**Decision:** `DeterministicAgent` owns semantic routing, session context,
response selection, and assessment orchestration. `ExecutionEngine` owns the
infrastructure investigation.

**Consequence:** Deterministic reasoning and safety remain code paths; the model
is replaceable without changing collection authority.

> Detailed records: `docs/adr/ADR-0001-agent-responsibility-boundary.md` and
> `docs/adr/ADR-0007-deterministic-pipeline.md`.

## AD-018 — Project RAG is isolated from Chat

**Decision:** RAG is available through explicit project API/UI operations and
is never registered as a chat Child Tool.

**Consequence:** Each project owns separate documents, indexes, and analysis
history. Each analysis receives request-scoped model configuration.

## AD-019 — Model lifecycle is external to Orion

**Decision:** Orion stores/tests connections but does not install model
runtimes or weights.

**Consequence:** Orion can start without a model. Chat assessment and RAG
analysis report setup-required behavior until a compatible endpoint is active.

## AD-020 — Evidence validity and provenance are explicit

**Decision:** Command, capability, evidence, Fact, and Finding contracts
distinguish valid, empty, partial, failed, unsupported, stale, and contradictory
states.

**Consequence:** Only valid fresh evidence satisfies requirements; claims retain
source links and failures cannot become healthy default values.

> Detailed record: `docs/adr/ADR-0008-evidence-validity.md`

## AD-021 — Deterministic reasoning is bounded and reviewed

**Decision:** Orion uses reviewed atomic/composite rules, declared recovery
alternatives, one bounded missing-evidence expansion, and a shared execution
budget.

**Consequence:** Rules carry version/owner/review metadata; unavailable evidence
remains insufficient rather than false.

> Detailed record: `docs/adr/ADR-0009-deterministic-reasoning-v1.md`

## AD-022 — Current external facts require deterministic verification

**Decision:** Current public information and explicit URLs use the fixed
Internet search/fetch evidence path.

**Consequence:** External answers carry provider/URL/retrieval provenance.
Unavailable verification is reported as unknown rather than replaced by model
memory.

> Detailed record: `docs/adr/ADR-0010-deterministic-external-verification.md`
