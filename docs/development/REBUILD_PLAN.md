# Greenfield rebuild plan

## Strategy

Build the new runtime as a small coherent core, migrate reusable executors/storage behind new interfaces, cut entrypoints over, then delete the old architecture. Do not preserve dual semantics indefinitely.

## Phase 0 — audit and freeze target

- Complete `CODE_AUDIT_BRIEF.md`.
- Record KEEP/ADAPT/REWRITE/DELETE matrix.
- Identify external compatibility requirements that truly must survive.
- Freeze capability inventory and target/source configuration semantics.

Exit: no unknown production execution path remains unclassified.

## Phase 1 — canonical contracts

Implement and test, with no real side effects:

- `CapabilityDefinition` and registry;
- exact TargetRegistry/SourceRegistry;
- ModelTurn/ToolCall/ToolResult/FinalMessage contracts;
- EvidenceRecord/EvidenceStore;
- AuthorityDecision, PermissionDecision, ApprovalRecord, Budget;
- canonical events.

Exit: contract tests and static checks green.

## Phase 2 — model-native runtime with fake executor

Implement:

- dynamic tool exposure;
- provider-neutral model backend;
- one-tool-call-per-turn loop;
- exposure/schema validation;
- authority/permission/approval/budget pipeline;
- duplicate/no-progress handling;
- final evidence-ref validation.

Use fake model + fake executors first.

Exit: deterministic vertical-slice tests green.

## Phase 3 — migrate read-only executors

Adapt or rewrite:

- deterministic calculator;
- host reads;
- Grafana reads;
- Zabbix reads;
- project/RAG retrieval;
- internet reads.

Every executor goes through the same registry/authority/evidence path.

Exit: no read capability bypasses canonical runtime.

## Phase 4 — writes, approval, and isolation

Add reviewed write capabilities one by one. Bind approvals to action fingerprints. Introduce least-privilege credentials and execution isolation appropriate to each backend.

Exit: write tests prove deny/ask/allow, exact refs, duplicate safety, and post-action evidence.

## Phase 5 — persistence/API/UI/CLI cutover

- Persist typed timeline/evidence/approval state.
- Cut Web and CLI to the new runtime.
- Update UI for typed tool/approval/evidence items.
- Generate new OpenAPI.

Exit: all user entrypoints use one runtime.

## Phase 6 — remove old architecture

Delete old model decision FSM, semantic routers, old capability bridges, duplicate event/metrics truths, stale tests, dead configs, and compatibility shims that have no external requirement.

Exit: static reachability shows no old runtime execution path.

## Phase 7 — validation ladder

1. focused unit/contract suite;
2. repository static/lint/type suite;
3. fake E2E vertical slices;
4. Docker service integration;
5. one live model probe per major flow;
6. smoke QA;
7. broader release/GA2 only after first real failures are resolved.

Do not compensate for live-model protocol failures by adding hidden state-machine prompts. Simplify the model surface instead.
