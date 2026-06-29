# Model Specification
# Model: LifecycleState
---
# Purpose
LifecycleState represents the current lifecycle state of a single execution.
It provides an immutable snapshot of the execution lifecycle at a specific point in time.
---
# Ownership
LifecycleState is owned by the Shared layer.
---
# Fields
| Field     | Type               |
|-----------|--------------------|
| state     | ExecutionState     |
| timestamp | float              |
| metadata  | dict[str, object] \| None |
---
# Constraints
LifecycleState:
- is immutable;
- is implemented as a frozen dataclass;
- uses slots;
- contains no business logic;
- contains no validation logic;
- contains no helper methods.
---
# Relationships
LifecycleState references:
- ExecutionState
LifecycleState is consumed by:
- LifecycleManager
- LifecycleTransition
- ResultCollector
- Runtime diagnostics
