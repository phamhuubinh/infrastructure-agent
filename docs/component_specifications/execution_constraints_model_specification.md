# Model Specification
# Model: ExecutionConstraints
---
# Purpose
ExecutionConstraints defines the execution limits and policies applied by the Runtime during execution.
It provides immutable constraints used to control execution behavior.
---
# Ownership
ExecutionConstraints is owned by the Shared layer.
---
# Fields
| Field           | Type |
| --------------- | ---- |
| timeout_seconds | int  |
| cancellable     | bool |
---
# Constraints
ExecutionConstraints:
* is immutable;
* applies to one execution;
* shall contain only execution constraint values;
* shall not be modified after creation.
---
# Relationships
ExecutionConstraints references no other shared models.
ExecutionConstraints is consumed by:
* Runtime
* Executor
