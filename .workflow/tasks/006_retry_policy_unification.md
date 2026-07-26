# Task 006: Retry Policy Unification

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 6 (Sprint 2, P1 - Foundation)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

Retry logic exists but is distributed across 6+ independent implementations:
- `src/pipeline/execution_plan.py` — retry in execution plan
- `src/pipeline/execution_graph.py` — retry in graph execution
- `src/pipeline/target_resolver.py` — retry in target resolution
- `src/backend/db.py` — retry in database operations
- `src/tool/RAGTool/app/agent/langgraph_agent.py` — retry in RAG agent
- `src/cli/main.py` — retry in CLI

Each has different backoff strategies, retry counts, and error classification. Infrastructure tools are inherently flaky (network timeouts, API rate limits) — consistent retry is needed.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/pipeline/retry.py` (NEW) | `RetryPolicy` dataclass + `RetryExecutor` | ~80 lines |
| 2 | `src/pipeline/execution_runtime.py` | Integrate `RetryExecutor` | ~15 lines |
| 3 | `src/pipeline/execution_plan.py` | Replace distributed retry with centralized | ~10 lines removed |
| 4 | `src/pipeline/execution_graph.py` | Replace distributed retry | ~10 lines removed |
| 5 | `src/pipeline/target_resolver.py` | Replace distributed retry | ~10 lines removed |
| 6 | `src/backend/db.py` | Replace distributed retry | ~10 lines removed |

**Total estimated change:** ~135 lines

---

## 3. Detailed Instructions

### 3.1 `src/pipeline/retry.py` (NEW)

```python
from __future__ import annotations

import asyncio
import time
import random
from dataclasses import dataclass, field
from typing import Callable, TypeVar, Any

T = TypeVar("T")

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_base: float = 1.0   # seconds
    backoff_max: float = 30.0   # seconds
    jitter: float = 0.1         # ±10% jitter
    retryable_exceptions: tuple[type[Exception], ...] = (
        TimeoutError,
        ConnectionError,
        OSError,
    )

class RetryExecutor:
    """Unified retry with exponential backoff + jitter."""
    
    def __init__(self, policy: RetryPolicy | None = None):
        self.policy = policy or RetryPolicy()
    
    def execute(self, fn: Callable[[], T], context: str = "") -> T:
        """Execute fn with retry per policy. Re-raises last exception on exhaustion."""
        last_exc: Exception | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                return fn()
            except self.policy.retryable_exceptions as exc:
                last_exc = exc
                if attempt == self.policy.max_attempts:
                    break
                delay = min(
                    self.policy.backoff_base * (2 ** (attempt - 1)),
                    self.policy.backoff_max,
                )
                jitter = random.uniform(-self.policy.jitter, self.policy.jitter)
                time.sleep(delay + delay * jitter)
        raise last_exc  # type: ignore[misc]
```

### 3.2 Integration

In `execution_runtime.py`:
```python
retry = RetryExecutor(RetryPolicy(max_attempts=3))
result = retry.execute(lambda: tool.execute(args), context=f"node_{node_id}")
```

---

## 4. Verification Criteria

- [ ] All 6 distributed retry locations replaced with centralized `RetryExecutor`
- [ ] Pipeline execution time <10% increase for successful first-attempt calls
- [ ] Retry with exponential backoff + jitter verified (mock flaky endpoint)
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] New tests: `tests/pipeline/test_retry.py`
- [ ] One atomic commit: `feat: add unified retry policy + RetryExecutor`