# Task 001: ADR-0001 Reconciliation

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 1 (Sprint 1, P0 - Foundation)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

ADR-0001 (`docs/adr/ADR-0001-agent-responsibility-boundary.md`) describes a **model-driven iterative architecture**:
- "The reasoning model decides whether to continue execution or produce the final answer"
- "Execution becomes an iterative Action → Observation loop"
- The Agent "receives actions" and "executes commands" — implying a ReAct-style loop

The actual implementation (`src/agent/deterministic_agent.py`, 648 LOC) is a **deterministic single-pass pipeline**:
- `_should_pipeline()` — 8-condition routing decision tree (not a model decision)
- `run()` → `ExecutionEngine.execute()` → `_assess()` — single deterministic pass
- LLM is called only at the end for evidence interpretation (per ADR-0002)
- No model decides "whether to continue execution" — the pipeline runs to completion

ADR-0002 was written **after** this architecture shift and correctly documents the LLM-assessment-only constraint. But ADR-0001 was never updated, so it describes an architecture that **does not exist in the codebase**. If a future contributor implements ADR-0001 literally, they will build a ReAct loop — exactly what Orion intentionally rejected.

Additionally, **AD-020** in `docs/ai/09_ARCHITECTURE_DECISIONS.md` (the short-form summary of ADR-0001) also repeats the incorrect "Action → Observation loop" language.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `docs/adr/ADR-0001-agent-responsibility-boundary.md` | Add SUPERSEDED banner + pointer to ADR-0002 and new pipeline ADR; update "Decision" and "Consequences" sections to reflect deterministic pipeline reality | ~20 lines added, ~10 lines modified |
| 2 | `docs/adr/ADR-0002-llm-assessment-only.md` | Add note in "Related ADRs" explaining that ADR-0002 supersedes ADR-0001's execution model description | ~5 lines added |
| 3 | `docs/ai/09_ARCHITECTURE_DECISIONS.md` (AD-020) | Update AD-020 text to reflect deterministic pipeline (replace "Action → Observation loop" with accurate description) | ~5 lines modified |
| 4 | `docs/adr/ADR-0007-deterministic-pipeline.md` (NEW) | New ADR documenting the 6-stage deterministic pipeline architecture, the 8-condition `_should_pipeline()` routing, and the single-pass execution model | ~80 lines |
| 5 | `docs/adr/ADR-0003-knowledge-tool-single-entry-point.md` | Update "Related ADRs" cross-reference to point to ADR-0007 instead of outdated ADR-0001 description | ~2 lines modified |
| 6 | `docs/adr/ADR-0004-stateless-state-management.md` | Update cross-reference to point to ADR-0007 instead of outdated ADR-0001 description | ~2 lines modified |

**Total estimated change:** ~120 lines (documentation only, zero code changes)

---

## 3. Detailed Instructions Per File

### 3.1 `docs/adr/ADR-0001-agent-responsibility-boundary.md`

**Action:** Add SUPERSEDED banner at top, update "Decision" and "Consequences" sections.

**Current "Decision" section (lines 16-26):**
```
The Agent is an execution engine.
The Agent executes model-generated actions.
The Agent returns raw observations.
The Agent never decides what the next action should be.
The reasoning model decides whether to continue execution or produce the final answer.
The Agent never performs reasoning.
The Agent never generates actions.
The Agent never modifies actions.
The Agent never analyzes execution results.
The reasoning model owns all intelligence.
The Model is the only reasoning component.
```

**What's correct:** Lines about Agent never reasoning/planning/generating actions.
**What's wrong:** "The Agent executes model-generated actions" and "The reasoning model decides whether to continue execution" describe a model-driven iterative loop that doesn't exist.

**Changes needed:**

1. Add SUPERSEDED banner **after the `# Status` line** (before `---` separator on line 3 or as close as possible):
   ```
   # Status
   **⚠️ SUPERSEDED** — The execution model described in this ADR (model-driven iterative Action → Observation loop) was replaced by the deterministic single-pass pipeline documented in ADR-0007. See ADR-0002 for the companion decision that constrained the LLM to assessment-only. This ADR is retained for its security and responsibility-boundary decisions, which remain valid. The execution flow description in "Decision" and "Consequences" should not be treated as current architecture.
   Accepted
   ```

2. Revise the "Decision" section to acknowledge the evolution:
   - Keep: "The Agent is an execution engine", all "never" responsibilities
   - Remove: "The reasoning model decides whether to continue execution or produce the final answer"
   - Replace with: "**Note (2026-07-26):** The execution model has evolved from a model-driven iterative loop to a deterministic single-pass pipeline (see ADR-0007). The Agent still executes deterministically without reasoning — the change is that execution is now a pre-planned pipeline rather than a model-guided iteration."

3. Revise the "Consequences" section:
   - Remove: "Execution becomes an iterative Action → Observation loop rather than a single static execution plan."
   - Replace with: "**Note (2026-07-26):** The execution model is now a deterministic single-pass pipeline (see ADR-0007), not an iterative Action → Observation loop. The architecture remains model-agnostic — the assessment model can be swapped without changing the deterministic pipeline."

**Result:** File clearly warns readers not to implement the model-driven loop. Valid decisions (responsibility boundaries, safety, model-agnosticism) remain intact. Outdated execution model description is corrected inline.

---

### 3.2 `docs/adr/ADR-0002-llm-assessment-only.md`

**Action:** Add clarifying note in "Related ADRs" section.

**Changes needed:**

In the "Related ADRs" section (around line 55-57), add a note after the ADR-0001 reference:

```
- ADR-0001 (`docs/adr/ADR-0001-agent-responsibility-boundary.md`) — establishes the Agent as an execution engine. **Note:** ADR-0001's execution model description (iterative Action → Observation loop) was superseded by the deterministic pipeline architecture documented in ADR-0007. The responsibility boundaries defined in ADR-0001 remain valid.
```

This prevents confusion when someone reads ADR-0002's "Related ADRs" and follows the link to ADR-0001 expecting to find the current execution model.

---

### 3.3 `docs/ai/09_ARCHITECTURE_DECISIONS.md` — AD-020

**Action:** Update the short-form AD-020 to reflect reality.

**Current text (lines 84-89):**
```
## AD-020 — Agent is an execution engine, not a reasoning component
**Decision:** The Agent executes model-generated actions and returns raw observations; it never reasons, plans, generates commands, or analyzes results. All intelligence belongs to the reasoning model.
**Context:** The project originally explored an autonomous-agent architecture where the Agent would reason and plan independently.
**Reason:** Separating execution from reasoning keeps the Agent deterministic, predictable, and model-agnostic. The reasoning model can be swapped without changing the Agent.
**Consequence:** Architecture follows an Action → Observation loop. The Agent is a pure execution engine. New reasoning models can replace existing ones without modifying the Agent.
```

**Changes needed:**

Replace the "Consequence" line:
- Old: `**Consequence:** Architecture follows an Action → Observation loop.`
- New: `**Consequence:** Architecture follows a deterministic single-pass pipeline (see ADR-0007). The Agent is a pure execution engine. New reasoning models can replace existing ones without modifying the Agent.`

The "Decision" text is actually mostly correct (it says Agent never reasons, plans, generates commands) — but "executes model-generated actions" is slightly misleading since actions are generated deterministically by the pipeline, not by a model. However, changing this would be a larger rewrite of AD-020, and the long-form ADR-0001 already carries the SUPERSEDED banner. The minimal fix to AD-020 is just correcting the "Consequence" line.

---

### 3.4 `docs/adr/ADR-0007-deterministic-pipeline.md` (NEW FILE)

**Action:** Create a new ADR documenting the actual deterministic pipeline architecture.

**Proposed content:**

```markdown
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
1. **Normalize** (`src/pipeline/normalizer.py`) — Semantic normalization of user request (language, concept extraction, action classification). Config-driven via `config/concepts.yaml`.
2. **Intent Resolution** (`src/pipeline/intent_resolver.py`) — Deterministic keyword-based intent classification. 11 intent types (CPU, MEMORY, DISK, NETWORK, PROCESS, SERVICE, TROUBLESHOOTING, APPLICATION, MONITORING, PERFORMANCE, SECURITY).
3. **Target Resolution** (`src/pipeline/target_resolver.py`) — Resolve investigation target (localhost, specific hostname, or registered target). Fuzzy name matching for typo tolerance.
4. **Evidence Planning** (`src/pipeline/evidence_planner.py`, `capability_planner.py`) — Determine what evidence is needed. Concept + action → capability plan. Config-driven via `config/capability_plans.yaml`.
5. **Execution** (`src/pipeline/execution_engine.py`, `execution_plan.py`, `execution_graph.py`, `execution_runtime.py`) — Compile execution graph (DAG), execute nodes via KnowledgeTool, collect evidence.
6. **Assessment** (`DeterministicAgent._assess()`) — Build assessment request from collected evidence, run through LLM for interpretation. Short-circuit via `DeterministicResponder` for simple factual queries.

## Pipeline Routing
The `_should_pipeline()` method in `DeterministicAgent` determines whether a user request enters the pipeline or falls through to general chat. The decision tree has 8 conditions:
1. Knowledge questions → chat
2. Conversational/yes-no questions with MACHINE_ASSESSMENT intent → chat (unless vague health check)
3. Vague health checks (e.g., "có vấn đề gì không?") → pipeline
4. HIGH/MEDIUM confidence infrastructure intents → pipeline
5. LOW confidence → Tier-2 LLM classifier
6-8. (Additional routing for chat fallback, conversational patterns, equivalence markers)

## Single-Pass Model
The pipeline executes exactly once per user request. There is no iteration, no "decide whether to continue," and no model-guided tool selection. If the evidence is insufficient, the assessment output flags it — the user can request re-investigation, which triggers a new pipeline invocation.

## LLM Role
The LLM is used in exactly three places, all outside the pipeline execution:
1. **Assessment** — interpreting collected evidence (per ADR-0002)
2. **Tier-2 Classification** — classifying ambiguous queries (LOW confidence) as infrastructure vs. general
3. **Chat** — `assess_raw()` for general conversation and `chat()` method

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
- Pipeline stages are coupled through `InvestigationRequest` mutation (see ADR-0009 — Immutable Pipeline State, planned).
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
```

---

### 3.5 `docs/adr/ADR-0003-knowledge-tool-single-entry-point.md`

**Action:** Update "Related ADRs" cross-reference.

In the "Related ADRs" section (around line 55-57 in ADR-0003), replace the ADR-0001 reference:
- Old: references ADR-0001 for execution engine foundation
- New: `- ADR-0001 (`docs/adr/ADR-0001-agent-responsibility-boundary.md`) — establishes the Agent as an execution engine (execution model superseded by ADR-0007).`

(Check exact wording in the file — since I read lines 1-60, the Related ADRs section may be at lines 70+. Let me verify by reading the rest of the file.)

### 3.6 `docs/adr/ADR-0004-stateless-state-management.md`

**Action:** Update cross-reference to ADR-0001.

In the ADR-0004 file, find the reference to ADR-0001 and add a note: "(execution model superseded by ADR-0007)".

---

## 4. Verification Criteria

After completing all changes:

1. **ADR-0001** has a clearly visible SUPERSEDED banner that cannot be missed.
2. **ADR-0001** inline "Decision" and "Consequences" text no longer describes a model-driven iterative loop.
3. **ADR-0002** cross-reference clarifies the relationship between ADR-0001 (responsibilities valid), ADR-0007 (pipeline architecture), and ADR-0002 (LLM constraint).
4. **ADR-0007** accurately describes the 6-stage pipeline, `_should_pipeline()` routing, and single-pass execution model — matching the actual implementation in `src/agent/deterministic_agent.py`.
5. **AD-020** no longer says "Action → Observation loop."
6. **ADR-0003** and **ADR-0004** cross-references are updated.
7. **`git diff`** shows only documentation changes — zero code changes.
8. **No test regressions** (this is a docs-only change, but verify with `python -m pytest tests/ -q --tb=short -x -k "not slow"` per development rules).

---

## 5. Dependencies

- None. This is the first Sprint 1 item and has no upstream dependencies.
- This item is a **prerequisite** for all subsequent Sprint 1 items (Items #2, #3, #12) — those items assume the architecture is correctly documented.

---

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| ADR-0007 content doesn't match actual implementation | Low | ADR-0007 is based on verified source code (`deterministic_agent.py`, pipeline modules). Review before commit. |
| Cross-reference chain breaks (dead links) | Very Low | All references use relative file paths. Verify with `grep` after changes. |
| Someone reads ADR-0001 without seeing SUPERSEDED | Low | Banner is placed at the top, immediately visible. Inline corrections reinforce the message. |

---

## 7. Effort Estimate

- **LOC:** ~120 lines (documentation only)
- **Complexity:** Low (no code changes, no tests needed)
- **Time:** ~30 minutes (write ADR-0007 + update 5 existing files + verify)

---

## 8. Acceptance Criteria

- [x] Item defined in this document
- [ ] ADR-0001 has SUPERSEDED banner + inline corrections
- [ ] ADR-0002 has updated cross-reference note
- [ ] AD-020 in `09_ARCHITECTURE_DECISIONS.md` corrected
- [ ] ADR-0007 created with accurate pipeline documentation
- [ ] ADR-0003 and ADR-0004 cross-references updated
- [ ] `git diff` shows only docs changes, zero code changes
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] `08_PROJECT_STATE.md` updated (Next milestones section: note Sprint 1 in progress)
- [ ] `.workflow/state.json` updated (backlog populated with Item 001 as in-progress)
- [ ] One atomic git commit with message: `docs: reconcile ADR-0001 with deterministic pipeline architecture`