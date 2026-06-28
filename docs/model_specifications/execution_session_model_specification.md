# Model Specification
# Model: ExecutionSession
---
# Purpose
ExecutionSession groups one or more executions into a single execution session.
It provides a shared identity and lifecycle for related executions.
---
# Ownership
ExecutionSession is owned by the Shared layer.
---
# Lifetime
One execution session.
---
# Fields
| Field         | Type              |
| ------------- | ----------------- |
| session_id    | str               |
| execution_ids | tuple[str, ...]   |
| created_at    | datetime          |
| state         | ExecutionState    |
| metadata      | dict[str, object] |
---
# Constraints
ExecutionSession:
* is immutable;
* owns exactly one session identifier;
* may reference one or more executions;
* shall not be modified after creation.
---
# Relationships
ExecutionSession references:
* ExecutionState
ExecutionSession is consumed by:
* Runtime
* Executor
