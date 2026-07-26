# Task 004: Capability-Level Security Pipeline

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 4 (Sprint 2, P1 - Foundation)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

Orion has zero runtime safety checks. `KnowledgeTool.execute()` dispatches directly to child tools via `_dispatch()`. The `chat()` method in `DeterministicAgent` bypasses `KnowledgeTool` entirely — it calls `self._assessment_model.assess_raw(prompt)` directly, creating a naked LLM call path with no capability validation, no tool dispatch, and no security checks.

Current safety comes from limitation (capabilities happen to be read-only), not from design. Adding a state-mutating capability would have no architectural enforcement.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/pipeline/security/inspector.py` (NEW) | `ToolInspector` ABC + Allow/Deny/RequireApproval types | ~40 lines |
| 2 | `src/pipeline/security/read_only.py` (NEW) | `ReadOnlyInspector` — validates capabilities don't mutate state | ~40 lines |
| 3 | `src/pipeline/security/target_inspector.py` (NEW) | `TargetInspector` — validates tool called against expected target | ~50 lines |
| 4 | `src/pipeline/security/param_safety.py` (NEW) | `ParameterSafetyInspector` — validates params against dangerous patterns | ~40 lines |
| 5 | `src/pipeline/security/chain.py` (NEW) | `InspectorChain` — runs inspector sequence on each tool call | ~30 lines |
| 6 | `src/tool/knowledge_tool.py` | Insert inspector chain in `_dispatch()` method | ~15 lines |
| 7 | `src/agent/deterministic_agent.py` | Add guard in `chat()` method to prevent dangerous prompts | ~15 lines |
| 8 | `src/shared/capability.py` | Add `mutation_risk` field to `Capability` dataclass | ~5 lines |

**Total estimated change:** ~235 lines

---

## 3. Detailed Instructions

### 3.1 `src/pipeline/security/inspector.py` (NEW)

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

class InspectorResult(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"

@dataclass
class InspectionReport:
    result: InspectorResult
    reason: str = ""
    inspector_name: str = ""

class ToolInspector(ABC):
    """Abstract base for tool execution safety inspectors."""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def inspect(self, capability_name: str, target: str, params: dict) -> InspectionReport:
        """Return ALLOW, DENY, or REQUIRE_APPROVAL."""
        ...
```

### 3.2 `ReadOnlyInspector`

Check `Capability.mutation_risk` field — deny if mutation_risk > 0.

### 3.3 `TargetInspector`

Validate target is in registry with correct type. Prevent calling production tools against dev targets.

### 3.4 `ParameterSafetyInspector`

Check parameters for dangerous patterns: `rm -rf`, `dd`, injection markers, path traversal.

### 3.5 Integration in `knowledge_tool.py`

Insert before the `_dispatch()` call:

```python
# Before line ~85 in KnowledgeTool.execute():
inspector_result = self._inspection_chain.inspect(
    capability_name=str(source),
    target=str(self._registry.get_target_name()),
    params=arguments
)
if inspector_result == InspectorResult.DENY:
    return ToolResult(success=False, error=inspector_result.reason)
```

### 3.6 Guard in `deterministic_agent.py` `chat()` method

Add input validation before `assess_raw()`:
```python
def chat(self, user_message: str) -> str:
    # Security: prevent system prompt injection in chat path
    if self._has_dangerous_patterns(user_message):
        return "Tôi không thể thực hiện yêu cầu này vì lý do bảo mật."
    return self._assessment_model.assess_raw(user_message)
```

### 3.7 `mutation_risk` field in Capability

Add to `src/shared/capability.py`:
```python
@dataclass
class Capability:
    ...
    mutation_risk: int = 0  # 0=read-only, 1=state-change, 2=destructive
```

---

## 4. Verification Criteria

- [ ] All tool execution paths pass through inspector chain
- [ ] `chat()` path has prompt guard
- [ ] Inspector chain latency <5ms per tool call
- [ ] All existing capabilities ALLOW by default (no regression)
- [ ] 100% coverage: `python -m pytest tests/pipeline/security/`
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] New ADR created: `docs/adr/ADR-0008-security-inspector-chain.md`
- [ ] One atomic commit: `feat: add capability-level security pipeline with inspector chain`