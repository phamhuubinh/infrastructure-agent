# Model Specification
# Model: ExecutionContext
---
# Purpose
ExecutionContext contains the immutable information required for a single execution.
It provides the Runtime with the execution parameters and metadata required during execution.
---
# Ownership
ExecutionContext is owned by the Shared layer.
---
# Lifetime
One execution.
---
# Fields
| Field        | Type              |
| ------------ | ----------------- |
| execution_id | str               |
| parameters   | dict[str, object] |
| metadata     | dict[str, object] |
---
# Constraints
ExecutionContext:
* is immutable;
* belongs to exactly one execution;
* shall contain one execution identifier;
* shall not be modified after creation.
---
# Relationships
ExecutionContext references no other shared models.
ExecutionContext is consumed by:
* Runtime
* Executor
* Tool
