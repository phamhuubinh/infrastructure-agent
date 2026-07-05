# Model Specification
# Model: ExecutionState
---
# Purpose
ExecutionState represents the lifecycle state of a single execution.
It defines the valid execution states shared by the Runtime, Executor, and Verification layers.
---
# Ownership
ExecutionState is owned by the Shared layer.
---
# Definition
ExecutionState is an enumeration.
---
# Values
* CREATED
* READY
* RUNNING
* COMPLETED
* FAILED
* CANCELLED
* TIMEOUT
---
# Constraints
ExecutionState:
* is immutable;
* represents exactly one lifecycle state;
* shall contain only the defined enumeration values;
* shall not contain additional metadata.
---
# Relationships
ExecutionState is referenced by:
* ExecutionResult
* ExecutionSession
* LifecycleState
* LifecycleTransition
* LifecycleManager
* TransitionPolicy
