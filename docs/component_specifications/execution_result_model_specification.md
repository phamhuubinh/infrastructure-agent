# Model Specification
# Model: ExecutionResult
---
# Purpose
ExecutionResult represents the immutable outcome of a completed execution.
It provides the standardized execution result shared by the Runtime, Executor, and Verification layers.
---
# Ownership
ExecutionResult is owned by the Shared layer.
---
# Fields
| Field        | Type            |
|--------------|-----------------|
| execution_id | str             |
| state        | ExecutionState  |
| output       | object          |
| error        | str             |
| metadata     | RuntimeMetadata |
---
# Constraints
ExecutionResult:
- is immutable;
- represents exactly one execution;
- shall contain one execution identifier;
- shall not be modified after creation.
The execution state should represent a terminal execution state.
---
# Relationships
ExecutionResult references:
- ExecutionState
- RuntimeMetadata
ExecutionResult is consumed by:
- Runtime
- Verification
