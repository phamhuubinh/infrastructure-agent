# 10 - Phase 6 Plan: Pipeline Architecture Hardening

> Historical delivery status: **Completed (2026-07-24)**. All 32 task IDs across 9 work
> packages produced the recorded implementation artifacts. This does **not** mean every current
> end-to-end behavior satisfies the newer DR1 acceptance criteria.
> Generated: 2026-07-24. Reconciled: 2026-08-05 (`DR1-006`).

## Context

Three rounds of evaluation testing revealed 48 distinct issues across the pipeline. The root cause analysis confirmed that while **Evidence Collection** works well, the layers above it — Intent Resolution, Capability Routing, Tool Selection, Parameter Extraction, Answer Type Classification, Evidence Reuse, and Assessment Quality — all have critical gaps.

This document defines the concrete implementation plan to close those gaps.

## Reference Documents

| Doc | Relevance |
|-----|-----------|
| `docs/ai/01_VISION.md` | Target philosophy: "Code investigates. AI explains." |
| `docs/ai/02_CURRENT_ARCHITECTURE.md` | Current pipeline stages |
| `docs/ai/05_EXECUTION_PIPELINE.md` | 6-stage pipeline specification |
| `docs/ai/07_DEVELOPMENT_RULES.md` | Mandatory engineering rules |
| `docs/ai/08_PROJECT_STATE.md` | Current implementation status |
| `docs/project/DETERMINISTIC_REASONING_BACKLOG.md` | Active corrective backlog and current acceptance criteria |

## DR1-006 reconciliation (2026-08-05)

Phase 6 remains a completed **historical delivery milestone**: commits `c68dad4`, `70f9943`,
`2c04422`, `1982b81`, and `0a34649` added the recorded modules and tests. DR1-006 separately
checked all IDs 601–632 against the current source, focused tests, and the DR1-005 stage-level
baseline. The distinction used below is:

- **Artifact present:** the file, field, hook, or unit-level behavior delivered by Phase 6 still
  exists. This preserves the historical completion record.
- **Open behavior correction:** an end-to-end acceptance gap is observable in current source or
  QA and is owned by the linked DR1 task. It does not imply that the Phase 6 artifact is absent.
- A test of a parser or standalone class proves that local contract only. It does not prove that
  the value affects capability execution, evidence validity, or the final response.

All `DR1-*` references below point to the active
[Deterministic Reasoning backlog](../project/DETERMINISTIC_REASONING_BACKLOG.md).

| Phase 6 ID | Current artifact and test evidence | Current behavioral reconciliation / corrective owner |
|---|---|---|
| 601 | Orion identity instructions remain in `config/prompts/chat_system.j2` and the model adapter system prompt. | Artifact present. Identity text itself has no focused output validator; response-wide claim grounding is covered by DR1-703. |
| 602 | `DeterministicAgent.run()` and `run_with_steps()` catch `UnknownTargetError` separately and do not use the chat fallback. Target/trace tests exercise the error path. | Artifact present. Resolver confidence and deterministic clarification remain under DR1-306 and DR1-309. |
| 603 | `TargetResolver` has the Step 4.5 hostname-like guard and focused unknown-target tests. | Artifact present, but the guard is heuristic: pure alphabetic/Vietnamese-preposition cases can still reach `localhost`. DR1-306 owns threshold, margin, and unknown-target behavior. |
| 604 | Vietnamese-only instructions remain in chat and assessment prompts. | Prompt enforcement is present; output validation is not. DR1-706 owns the language-quality validator, with grounding integration under DR1-703. |
| 605 | `CapabilityPlanner` is invoked from both execution paths and filters existing `capability_references` when names overlap. | Wiring exists, but routing still combines the classic resolver/planner and an LLM classifier fallback. DR1-301, DR1-302, and DR1-308 own deterministic routing and the unified request/status contracts. |
| 606 | `concepts.yaml` contains standalone hostname, kernel, uptime, and load concepts; port is represented through network/firewall synonyms. | The original database/port/zombie breadth is not present as equivalent standalone concepts, and QA still exposes normalization gaps. DR1-303 owns typo/code-switch/lexicon corrections; DR1-405 owns bounded multi-concept decomposition. |
| 607 | `capability_plans.yaml` contains plans for the Phase 6 concepts and `test_capability_planner.py` checks their local mappings. | Config artifacts are present, but plan correctness is still constrained by the split request/routing flow. DR1-302 and DR1-308 own the canonical planning inputs and statuses. |
| 608 | `capability_library.py` centralizes operational names and validates `COVERS_TO_OPERATIONAL`; router/resolver tests check mapping coverage. | Name consistency is present. Environment support and normalized Linux outputs remain open under DR1-204 and DR1-210. |
| 609 | `ParameterExtractor` extracts service, port, process, path, and time-range values; focused unit tests cover those parsers. | Parser artifact present; DR1-005 QA shows parameter accuracy is not sufficient end to end. DR1-403 owns binding and DR1-404 owns required-parameter validation. |
| 610 | Both engine paths store extracted parameters on the investigation/state and pass the object into `ExecutionRuntime.execute()`. | Transport to the runtime boundary is present, but this is not capability binding. DR1-302, DR1-402, and DR1-403 own the unified/context-aware parameter flow. |
| 611 | `extracted_params` reaches `ExecutionRuntime._execute_node()`. | The method currently builds `KnowledgeTool` arguments from only `source` and `resource`; extracted values do not filter the child capability. This is an open correction in DR1-403 and DR1-404. |
| 612 | `AnswerType` and its deterministic classifier exist with focused unit tests. | The enum/classifier does not yet represent the complete canonical request classes (including forecast/action/explanation). DR1-308 owns that contract; DR1-407 owns temporal guards. |
| 613 | Both engine paths classify and store `answer_type`. | Integration hook exists, while authoritative routing/evidence/strategy statuses remain open in DR1-308. |
| 614 | `_assess()` attempts `DeterministicResponder` first, including for non-assessment answer types. | A failed fast-path attempt still falls through to LLM and the responder reads legacy raw dictionaries. Required-fact gating is owned by DR1-505 and DR1-707; assessment input by DR1-701. |
| 615 | `ToolSelector` and `ToolCategory` exist; focused tests cover directive/concept selection. | The selector returns a category without confidence/candidates and defaults unknown infrastructure to Linux. Deterministic routing corrections are owned by DR1-301, DR1-305, and DR1-308. |
| 616 | Both engine paths call `ToolSelector.select()` and store `selected_tool`. | `selected_tool` does not select `CapabilityRouter` routes; it is currently consumed mainly as a merge label. DR1-301, DR1-302, and DR1-308 own end-to-end route authority. |
| 617 | `EvidencePackage.source_tool` and `EvidenceMerge` tagging exist. | The mutable path labels all packages with one selected category rather than actual per-capability provenance, and the immutable merge path does not pass that label. DR1-508 and DR1-509 own evidence failures/provenance. |
| 618 | `_check_hostname()` exists in `DeterministicResponder`. | Artifact present; there is no focused hostname responder test and no canonical validity/freshness gate. DR1-501, DR1-502, DR1-505, and DR1-707 own the fact-backed response path. |
| 619 | `_check_kernel()` exists in `DeterministicResponder`. | Artifact present with the same raw-evidence/test gap as 618. Corrective owners: DR1-501, DR1-502, DR1-505, and DR1-707. |
| 620 | `_check_top_cpu()` exists in `DeterministicResponder`. | Artifact present with the same raw-evidence/test gap as 618. Corrective owners: DR1-106, DR1-501, DR1-502, and DR1-707. |
| 621 | `_check_ram_available()` exists in `DeterministicResponder`. | Artifact present, but legacy `or` fallbacks and computed zero can collapse missing/valid-zero semantics. DR1-106, DR1-501, DR1-505, and DR1-707 own the correction. |
| 622 | `_check_load_average()` exists and is called from `try_response()`. | Artifact present; canonical metric/unit/validity checks are still absent. DR1-501, DR1-502, DR1-505, and DR1-707 own the correction. |
| 623 | Thread-safe, per-instance `EvidenceCache` with a default 60-second TTL exists; unit tests cover target separation and expiry. | Local cache contract is present. Parameter/time/schema-aware keys and freshness policy are open in DR1-507. |
| 624 | `ExecutionEngine` removes cached nodes and caches packages whose legacy `success` boolean is true. | Integration exists, but boolean success cannot distinguish partial/failed validity and the key omits params/timeframe. DR1-108 and DR1-507 own the correction. |
| 625 | `runtime_factory` creates one cache per agent/session and passes it to both `ExecutionEngine` and `DeterministicAgent`. | Wiring is present. Safe reuse semantics remain dependent on DR1-108 and DR1-507. |
| 626 | `AssessmentResult.severity` exists. | The field is not populated by the assessment pipeline. Finding severity and assessment/output semantics are owned by DR1-604, DR1-701, and DR1-708. |
| 627 | Standalone `ThresholdEvaluator` and unit tests exist. | No production pipeline call site exists, and rules read heterogeneous raw keys. DR1-601 and DR1-603 own canonical atomic-rule inputs and unknown/failed semantics. |
| 628 | The prompt builder includes stronger Vietnamese instructions. | The broader original task (threshold injection, failed-evidence visibility, anti-hallucination enforcement) is not an end-to-end guard. DR1-702, DR1-703, DR1-705, and DR1-706 own those corrections. |
| 629 | Standalone `EvidenceCorrelation` and unit tests exist. | No production pipeline call site exists and it consumes raw evidence/severity-name dictionaries. DR1-604 and DR1-605 own Finding integration and output/trace impact. |
| 630 | `TimeRangeResolver` exists with focused tests for relative/day/week expressions. | Parser artifact present; a canonical timezone-aware `TimeRange` shared by requirements and capabilities remains open in DR1-406, with history guards in DR1-407. |
| 631 | `GrafanaTool.build_links()` accepts a resolved range and adds Grafana `from`/`to` URL parameters. | This is deep-link construction, not a time-series evidence query, and it has no focused link-range test. DR1-406, DR1-407, and DR1-503 own temporal evidence and Grafana fact normalization. |
| 632 | `_build_tool_links()` resolves a range and appends available tool links after assessment. | Link wiring exists, but it is not an embed/image response replacing text and does not guarantee time-series sufficiency. DR1-308, DR1-407, and DR1-707 own strategy/guard/response behavior. |

This matrix is the authoritative interpretation of the Phase 6 completion statement. The work
package tables below are retained as the original plan/delivery record, not as a claim that all
new DR1 acceptance criteria already pass.

## Target Architecture

```
User Request
     │
     ▼
┌──────────────────────────────────────┐
│ Normalizer (Phase 5 — ✅ Done)       │
│ Raw text → SemanticRequest           │
└────────────────┬─────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────┐
│ Parameter Extractor (Phase 6 — NEW)  │
│ Extract: service_name, port,         │
│ time_range, process_name, path       │
└────────────────┬─────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────┐
│ Answer Type Classifier (Phase 6 —    │
│ NEW)                                 │
│ Fact / List / Table / Chart /        │
│ Assessment / Comparison              │
└────────────────┬─────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────┐
│ Target Resolver (✅, needs fixes)    │
│ - Detect nonexistent hostnames       │
│ - Propagate UnknownTargetError       │
│ - Pattern-based normalization        │
└────────────────┬─────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────┐
│ Tool Selector (Phase 6 — NEW)        │
│ Route: Linux | Grafana | Zabbix | KB │
└────────────────┬─────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────┐
│ Capability Planner (Phase 5 ✅,      │
│ needs integration)                   │
│ concept+action → capability list     │
└────────────────┬─────────────────────┘
                 │
         ┌───────┴───────┐
         ▼               ▼
┌─────────────┐  ┌──────────────────┐
│ Evidence    │  │ Evidence Cache   │
│ Collection  │  │ (Phase 6 — NEW)  │
│ ✅ Done     │  │ TTL=60s, per     │
│             │  │ session reuse    │
└──────┬──────┘  └────────┬─────────┘
       │                  │
       └────────┬─────────┘
                ▼
    ┌───────────┴───────────┐
    ▼                       ▼
┌────────────────┐  ┌──────────────────────┐
│ Deterministic  │  │ Assessment Pipeline  │
│ Responder      │  │ (Phase 6 — expanded) │
│ (Phase 6 —     │  │                      │
│ expanded)      │  │ ┌──────────────────┐ │
│                │  │ │ Threshold        │ │
│ Fact / List /  │  │ │ Evaluator (NEW)  │ │
│ Table answers  │  │ └────────┬─────────┘ │
│                │  │          ▼           │
│                │  │ ┌──────────────────┐ │
│                │  │ │ Evidence         │ │
│                │  │ │ Correlation(NEW) │ │
│                │  │ └────────┬─────────┘ │
│                │  │          ▼           │
│                │  │ ┌──────────────────┐ │
│                │  │ │ Prompt Builder   │ │
│                │  │ │ (expanded)       │ │
│                │  │ └────────┬─────────┘ │
│                │  │          ▼           │
│                │  │ ┌──────────────────┐ │
│                │  │ │ LLM Assessment   │ │
│                │  │ └──────────────────┘ │
│                │  └──────────────────────┘
└───────┬────────┘            │
        │                     │
        └──────────┬──────────┘
                   ▼
          Final Response
```

## Root Cause: CapabilityPlanner Not Integrated

The `CapabilityPlanner` was created in Phase 5 (Task 510, `src/pipeline/capability_planner.py`) but was **never wired into** `ExecutionEngine.execute()`.

Current flow (broken):
```
IntentResolver (keyword) → EvidencePlanner (template) → CapabilityResolver
```

Intended flow (Phase 5 design):
```
Normalizer (language) → CapabilityPlanner → Capability list
```

`Normalizer` runs (`execution_engine.py:74`), `CapabilityPlanner` exists, but the connection between them is missing. The pipeline still uses the old `IntentResolver` → `EvidencePlanner` path exclusively.

**Fixing this is task 2.1 — the single highest-impact change in Phase 6.**

## Work Packages

### WP6.1: Bug Fixes 🔴 Critical
**Effort: 5h | Tasks: 4**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 601 | Fix identity leak — override model system prompt to "Orion" | `src/agent/deterministic_agent.py:464-468` | 1h |
| 602 | Propagate UnknownTargetError instead of falling back to chat | `src/agent/deterministic_agent.py:93-102` | 1h |
| 603 | TargetResolver: detect nonexistent hostnames, raise error | `src/pipeline/target_resolver.py:295-316` | 2h |
| 604 | Strengthen language enforcement (Vietnamese → Vietnamese only) | `src/agent/deterministic_agent.py:448-484`, `src/model/protocol/prompt_builder_v2.py:317-319` | 1h |

### WP6.2: CapabilityPlanner Integration 🟠 High
**Effort: 5h | Tasks: 4**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 605 | Wire CapabilityPlanner into ExecutionEngine.execute() | `src/pipeline/execution_engine.py:60-88` | 2h |
| 606 | Expand concepts.yaml: hostname, kernel, uptime, load, database, port, zombie | `config/concepts.yaml` | 1h |
| 607 | Expand capability_plans.yaml: new concept plans | `config/capability_plans.yaml` | 0.5h |
| 608 | Verify operational names in CapabilityLibrary | `src/pipeline/capability_library.py` | 1.5h |

### WP6.3: Parameter Extraction 🟠 High
**Effort: 4h | Tasks: 3**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 609 | Create ParameterExtractor module (service_name, port, time_range, process, path) | `src/pipeline/parameter_extractor.py` (new) | 2h |
| 610 | Integrate ParameterExtractor into ExecutionEngine + InvestigationRequest | `src/pipeline/execution_engine.py`, `src/pipeline/investigation_request.py` | 1h |
| 611 | Use extracted params to filter evidence collection (e.g., only nginx service) | `src/tool/linux/` tool files | 1h |

### WP6.4: Answer Type Classification 🟠 High
**Effort: 4h | Tasks: 3**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 612 | Create AnswerType enum + classifier (Fact/List/Table/Chart/Assessment/Comparison) | `src/pipeline/answer_type.py` (new) | 0.5h |
| 613 | Integrate AnswerType into pipeline (classify after Normalizer) | `src/pipeline/execution_engine.py` | 0.5h |
| 614 | Route by AnswerType in DeterministicAgent._assess(): Fact→deterministic, List→table, Chart→Grafana, Assessment→LLM | `src/agent/deterministic_agent.py:229-261` | 3h |

### WP6.5: Tool Selection 🟡 Medium
**Effort: 4h | Tasks: 3**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 615 | Create ToolSelector module (Linux/Grafana/Zabbix/KnowledgeBase/Internet) | `src/pipeline/tool_selector.py` (new) | 1.5h |
| 616 | Integrate ToolSelector into pipeline | `src/pipeline/execution_engine.py` | 1.5h |
| 617 | Tag evidence with source_tool to prevent cross-contamination | `src/pipeline/evidence_merge.py`, `src/pipeline/evidence_package.py` | 1h |

### WP6.6: DeterministicResponder Expansion 🟡 Medium
**Effort: 4h | Tasks: 5**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 618 | Add hostname deterministic response | `src/pipeline/deterministic_responder.py` | 0.5h |
| 619 | Add kernel version deterministic response | `src/pipeline/deterministic_responder.py` | 0.5h |
| 620 | Add top CPU process deterministic response | `src/pipeline/deterministic_responder.py` | 1h |
| 621 | Add RAM available deterministic response | `src/pipeline/deterministic_responder.py` | 0.5h |
| 622 | Add load average deterministic response + wire all into try_response() | `src/pipeline/deterministic_responder.py` | 0.5h |

### WP6.7: Evidence Cache 🟡 Medium
**Effort: 4h | Tasks: 3**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 623 | Create EvidenceCache class (per-session, TTL 60s) | `src/pipeline/evidence_cache.py` (new) | 1.5h |
| 624 | Integrate EvidenceCache into ExecutionEngine (check before execute) | `src/pipeline/execution_engine.py` | 1.5h |
| 625 | Integrate EvidenceCache into DeterministicAgent (reuse across turns) | `src/agent/deterministic_agent.py` | 1h |

### WP6.8: Assessment Quality 🟡 Medium
**Effort: 6h | Tasks: 4**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 626 | Add severity field to AssessmentResult (ok/info/warning/critical) | `src/model/assessment_result.py` | 0.5h |
| 627 | Create ThresholdEvaluator (disk>80%→warning, RAM>90%→warning, zombie≥1→warning) | `src/pipeline/threshold_evaluator.py` (new) | 2.5h |
| 628 | Update prompt builder: inject thresholds, filter loop devices, add anti-hallucination rules | `src/model/protocol/prompt_builder_v2.py` | 2h |
| 629 | Create EvidenceCorrelation (cross-evidence bottleneck detection) | `src/pipeline/evidence_correlation.py` (new) | 1h |

### WP6.9: Time Range & Visualization 🟢 Low
**Effort: 6h | Tasks: 3**

| ID | Task | Files | Effort |
|----|------|-------|--------|
| 630 | Create TimeRangeResolver ("1 giờ"→3600s, "today"→day start, "7d"→7 days ago) | `src/pipeline/time_range_resolver.py` (new) | 2h |
| 631 | Add Grafana time series query with time_range support | `src/tool/grafana/` | 2h |
| 632 | Build visualization response (Grafana embed link/image instead of text) | `src/agent/deterministic_agent.py` | 2h |

## Summary

| WP | Priority | Tasks | Effort |
|----|----------|-------|--------|
| WP6.1: Bug Fixes | 🔴 Critical | 4 | 5h |
| WP6.2: CapabilityPlanner | 🟠 High | 4 | 5h |
| WP6.3: Parameter Extraction | 🟠 High | 3 | 4h |
| WP6.4: Answer Type | 🟠 High | 3 | 4h |
| WP6.5: Tool Selection | 🟡 Medium | 3 | 4h |
| WP6.6: DeterministicResponder | 🟡 Medium | 5 | 4h |
| WP6.7: Evidence Cache | 🟡 Medium | 3 | 4h |
| WP6.8: Assessment Quality | 🟡 Medium | 4 | 6h |
| WP6.9: Time Range & Viz | 🟢 Low | 3 | 6h |
| **Total** | | **32** | **42h** |

## New Files to Create

| File | Purpose | WP |
|------|---------|----|
| `src/pipeline/parameter_extractor.py` | Extract params from user request | 6.3 |
| `src/pipeline/answer_type.py` | Answer type enum + classifier | 6.4 |
| `src/pipeline/tool_selector.py` | Route concept → tool | 6.5 |
| `src/pipeline/evidence_cache.py` | Per-session evidence cache | 6.7 |
| `src/pipeline/threshold_evaluator.py` | Severity rules from thresholds | 6.8 |
| `src/pipeline/evidence_correlation.py` | Cross-evidence bottleneck detection | 6.8 |
| `src/pipeline/time_range_resolver.py` | Parse time expressions → timestamps | 6.9 |

## New Test Files Required

| Test file | Covers |
|-----------|--------|
| `tests/pipeline/test_parameter_extractor.py` | WP6.3 |
| `tests/pipeline/test_answer_type.py` | WP6.4 |
| `tests/pipeline/test_tool_selector.py` | WP6.5 |
| `tests/pipeline/test_evidence_cache.py` | WP6.7 |
| `tests/pipeline/test_threshold_evaluator.py` | WP6.8 |
| `tests/pipeline/test_evidence_correlation.py` | WP6.8 |
| `tests/pipeline/test_time_range_resolver.py` | WP6.9 |
| `tests/agent/test_deterministic_agent.py` (add tests) | WP6.1, WP6.6 |
| `tests/pipeline/test_target_resolver.py` (add tests) | WP6.1 |
| `tests/pipeline/test_execution_engine.py` (add tests) | WP6.2 |

## Implementation Rules (from 07_DEVELOPMENT_RULES.md)

1. **No speculative features** — implement only what's in this plan
2. **One commit per task** — atomic, verifiable through `git diff`
3. **Deterministic before AI** — all new pipeline modules are deterministic
4. **Backward compatibility** — old flow must still work when Normalizer confidence < 0.4
5. **Test before commit** — run `python3 -m pytest tests/ -q --tb=short -x` after each task
6. **Lint before commit** — run `ruff check .`
7. **Update state** — after each task, update `08_PROJECT_STATE.md` when project status changes

## Expected Outcomes

| Metric | Before Phase 6 | After Phase 6 |
|--------|---------------|---------------|
| Target Resolution accuracy | ~60% | ~95% |
| Capability Routing accuracy | ~40% | ~90% |
| % queries needing LLM | ~95% | ~60% |
| Hallucination frequency | Common | Rare |
| Evidence reuse within session | 0% | Available (TTL 60s) |
| Assessment severity | None | ok/info/warning/critical |
| Chart/visualization support | None | Grafana embed links |
| Service filtering by name | None | nginx, docker, sshd... |
| Time range queries | Broken | 1h, today, 7d... |
| Unknown target detection | Fallback to localhost | Raises clear error |
| Language enforcement | Weak hint | Strong directive |
| Identity leak | Qwen/Alibaba visible | Orion identity |
