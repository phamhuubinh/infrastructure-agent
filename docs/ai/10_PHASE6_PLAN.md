# 10 - Phase 6 Plan: Pipeline Architecture Hardening

> Status: **Completed (2026-07-24)**. All 32 tasks across 9 work packages are implemented and verified.
> Generated: 2026-07-24

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
