# ADR-0007
# Status
Accepted
---
# Context
The original architecture (ADR-0001) described a model-driven iterative execution model where "the reasoning model decides whether to continue execution or produce the final answer" in an "Action → Observation loop." During implementation, it became clear that infrastructure investigation follows repeatable operational procedures and does not benefit from model-driven iteration.

The pipeline was redesigned as a deterministic single-pass architecture where:
- All investigation stages (intent resolution, target resolution, evidence planning, capability resolution, execution planning, execution graph compilation, and evidence collection) run without any LLM call.
- Only the final assessment step (interpreting collected evidence) uses the LLM (per ADR-0002).
- The 6-stage pipeline runs to completion in a single pass — no model decides "whether to continue."

This ADR documents the actual architecture as implemented in `src/agent/deterministic_agent.py` and the `src/pipeline/` modules.
---
# Decision
The Agent uses a deterministic single-pass pipeline for infrastructure investigation.

## Pipeline Stages
1. **Normalize** (`src/pipeline/normalizer.py`) — Build one immutable `RequestFrame` with concepts, operation, target raw/resolved slots, parameters, answer class, timeframe, confidence, ambiguity and ranked lexical evidence.
2. **Intent Resolution** (`src/pipeline/intent_resolver.py`) — Deterministic intent candidates with scores, compatibility, confidence and top-candidate margin.
3. **Target Resolution** (`src/pipeline/target_resolver.py`) — Exact/scoped aliases precede fuzzy candidates; both threshold and margin are required and explicit unknown/ambiguous targets cannot fall back to localhost.
4. **Evidence Planning** (`src/pipeline/evidence_planner.py`, `capability_planner.py`) — Determine what evidence is needed. Concept + action → capability plan. Config-driven via `config/capability_plans.yaml`.
5. **Execution** (`src/pipeline/execution_engine.py`, `execution_plan.py`, `execution_graph.py`, `execution_runtime.py`) — Compile execution graph (DAG), execute nodes via KnowledgeTool, collect evidence.
6. **Assessment** (`DeterministicAgent._assess()`) — Build assessment request from collected evidence, run through LLM for interpretation. Short-circuit via `DeterministicResponder` for simple factual queries.

## Pipeline Routing
`DeterministicAgent._route_request()` returns a first-class routing decision before execution:

1. **Resolved infrastructure** → deterministic investigation pipeline.
2. **Clarification required** → bounded template for the exact missing/ambiguous field; no evidence/model call.
3. **Unsupported action** → deterministic read-only refusal.
4. **Knowledge/general conversation** → separate chat subsystem.

## Single-Pass Model
The pipeline executes exactly once per user request. There is no iteration, no "decide whether to continue," and no model-guided tool selection. If the evidence is insufficient, the assessment output flags it — the user can request re-investigation, which triggers a new pipeline invocation.

## LLM Role
The LLM is used in exactly two places, both outside deterministic routing/execution:
1. **Assessment** — interpreting collected evidence (per ADR-0002)
2. **Chat** — `assess_raw()` for the separately routed general conversation subsystem

The LLM never participates in pipeline execution, tool selection, or evidence planning.
---
# Consequences

## Positive
- Pipeline execution is deterministic, testable, and benchmarkable without an LLM.
- Token usage is minimized — the LLM only sees collected evidence, not tool schemas or execution plans.
- Latency is predictable — one LLM call per investigation (assessment only).
- The pipeline can run offline with `MockAssessmentAdapter`.
- New capabilities can be added without changing the pipeline architecture.

## Negative
- The model cannot request additional evidence mid-assessment — it must work with what was collected.
- Pipeline stages are coupled through `InvestigationRequest` mutation.
- Adding a new investigation domain requires adding a new intent type and evidence requirements.

## Mitigations
- `EvidenceCompleteness` ensures the evidence package is as complete as possible before assessment.
- Assessment output can recommend re-investigation for insufficient evidence.
- Config-driven intent resolution (`concepts.yaml`) allows adding new concepts without code changes.
---
# Related ADRs
- ADR-0001 (`docs/adr/ADR-0001-agent-responsibility-boundary.md`) — **Superseded by this ADR** for execution model. Responsibility boundaries remain valid.
- ADR-0002 (`docs/adr/ADR-0002-llm-assessment-only.md`) — Constrains LLM to assessment only; complements this ADR's deterministic pipeline.
- ADR-0003 (`docs/adr/ADR-0003-knowledge-tool-single-entry-point.md`) — KnowledgeTool as single dispatch entry point for evidence collection.
- ADR-0004 (`docs/adr/ADR-0004-stateless-state-management.md`) — Stateless execution; each pipeline invocation is independent.
---
# Referenced Files
- `src/agent/deterministic_agent.py` — Agent with `_should_pipeline()` routing and `_assess()` assessment
- `src/pipeline/execution_engine.py` — Pipeline execution coordinator
- `src/pipeline/normalizer.py` — Semantic request normalization
- `src/pipeline/intent_resolver.py` — Deterministic intent classification
- `src/pipeline/target_resolver.py` — Target resolution with fuzzy matching
- `src/pipeline/evidence_planner.py` — Evidence requirement planning
- `src/pipeline/capability_planner.py` — Capability planning from concepts + actions
- `src/pipeline/deterministic_responder.py` — Deterministic short-circuit for simple queries
- `config/concepts.yaml` — Concept definitions for Normalizer
- `config/capability_plans.yaml` — Capability plans for CapabilityPlanner
