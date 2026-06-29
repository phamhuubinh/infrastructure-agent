# Model Specification
# Model: LifecycleTransition
---
# Purpose
LifecycleTransition represents one immutable lifecycle transition between two execution states.
It records how the execution lifecycle changes over time.
---
# Ownership
LifecycleTransition is owned by the Shared layer.
---
# Fields
| Field      | Type               |
|------------|--------------------|
| from_state | ExecutionState     |
| to_state   | ExecutionState     |
| timestamp  | float              |
| metadata   | dict[str, object] \| None |
---
# Constraints
LifecycleTransition:
- is immutable;
- is implemented as a frozen dataclass;
- uses slots;
- contains no business logic;
- contains no validation logic;
- contains no helper methods;
- The timestamp represents the time at which the lifecycle transition was created.
---
# Relationships
LifecycleTransition references:
- ExecutionState
LifecycleTransition is consumed by:
- LifecycleManager
- Runtime diagnostics
