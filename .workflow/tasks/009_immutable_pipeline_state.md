# Task 009: Immutable Pipeline State

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 9 (Sprint 3, P2 - Refactor)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

`InvestigationRequest` is mutated in-place through all pipeline stages. Each stage adds fields to the same mutable object, creating temporal coupling — a stage's output depends on which previous stages have run. The `_build_pipeline_steps()` in `deterministic_agent.py` accesses `investigation.execution_plan.steps` without null-checking `execution_plan`, risking `AttributeError`.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/shared/pipeline_state.py` (NEW) | `PipelineState` immutable dataclass + `StateUpdate` dict type | ~50 lines |
| 2 | `src/pipeline/normalizer.py` | Return `StateUpdate` instead of mutating request | ~10 lines modified |
| 3 | `src/pipeline/intent_resolver.py` | Return `StateUpdate` instead of mutating request | ~10 lines modified |
| 4 | `src/pipeline/target_resolver.py` | Return `StateUpdate` | ~10 lines modified |
| 5 | `src/pipeline/evidence_planner.py` | Return `StateUpdate` | ~10 lines modified |
| 6 | `src/pipeline/capability_resolver.py` | Return `StateUpdate` | ~10 lines modified |
| 7 | `src/pipeline/capability_planner.py` | Return `StateUpdate` | ~10 lines modified |
| 8 | `src/pipeline/execution_engine.py` | Merge `StateUpdate` dicts between stages, manage `PipelineState` | ~30 lines modified |
| 9 | `src/agent/deterministic_agent.py` | `_build_pipeline_steps()` uses typed accessors with null-checking | ~15 lines modified |

**Total estimated change:** ~155 lines

---

## 3. Detailed Instructions

### 3.1 `src/shared/pipeline_state.py` (NEW)

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# A StateUpdate is a partial dict of fields that a stage contributes.
StateUpdate = dict[str, Any]

@dataclass(frozen=True)
class PipelineState:
    """Immutable pipeline state — accumulated through stages.
    
    Each stage returns a StateUpdate (partial dict).
    PipelineEngine merges updates, producing a new PipelineState.
    """
    user_request: str = ""
    intent: Any = None
    confidence: Any = None
    target: str = ""
    matched_keywords: tuple[str, ...] = ()
    required_evidence: tuple = ()
    optional_evidence: tuple = ()
    capability_references: tuple = ()
    execution_plan: Any = None
    execution_graph: Any = None
    evidence: tuple = ()
    evidence_complete: bool = False
    missing_evidence: tuple[str, ...] = ()
    runtime_metrics: Any = None
    
    def apply(self, update: StateUpdate) -> PipelineState:
        """Return a new PipelineState with update applied."""
        return replace(self, **update)
    
    @classmethod
    def initial(cls, user_request: str) -> PipelineState:
        return cls(user_request=user_request)
```

### 3.2 Stage Interface Change

Each pipeline stage changes from mutation to return:

```python
# OLD (mutates request in-place):
def resolve(self, request: InvestigationRequest) -> None:
    request.intent = Intent.CPU_ASSESSMENT
    request.confidence = Confidence.HIGH

# NEW (returns StateUpdate):
def resolve(self, state: PipelineState) -> StateUpdate:
    return {
        "intent": Intent.CPU_ASSESSMENT,
        "confidence": Confidence.HIGH,
    }
```

### 3.3 PipelineEngine merge logic

```python
class ExecutionEngine:
    def execute(self, user_request: str) -> PipelineState:
        state = PipelineState.initial(user_request)
        
        # Stage 1: Normalize
        update = self._normalizer.normalize(state)
        state = state.apply(update)
        
        # Stage 2: Intent
        update = self._intent_resolver.resolve(state)
        state = state.apply(update)
        
        # ... repeat for all stages
        
        return state
```

### 3.4 Null-safety in `_build_pipeline_steps()`

```python
# OLD (line 166):
if investigation.execution_plan:
    for step in investigation.execution_plan.steps:

# NEW:
if state.execution_plan is not None:
    for step in state.execution_plan.steps:
```

---

## 4. Dependencies

- None hard-dependency, but benefits from Task #003 (Unified Config)
- Blocks: Task #010 (RAG Rationalization) — uses new pipeline state model

---

## 5. Verification Criteria

- [ ] All 9 pipeline stages return `StateUpdate` instead of mutating
- [ ] Each stage independently testable with just a `PipelineState` input
- [ ] Pipeline execution time <5% increase
- [ ] No `AttributeError` from null field access in `_build_pipeline_steps()`
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] One atomic commit: `refactor: migrate pipeline to immutable PipelineState`