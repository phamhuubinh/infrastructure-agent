# Model Specification
# Model: RuntimeMetadata
---
# Purpose
RuntimeMetadata contains immutable metadata describing a completed execution.
It records Runtime-specific information without containing execution results.
---
# Ownership
RuntimeMetadata is owned by the Shared layer.
---
# Fields
| Field           | Type     |
|-----------------|----------|
| runtime_version | str      |
| started_at      | datetime |
| finished_at     | datetime |
| duration_ms     | int      |
---
# Constraints
RuntimeMetadata:
- is immutable;
- describes one execution;
- shall not be modified after creation;
- contains Runtime metadata only.
---
# Relationships
RuntimeMetadata references no other shared models.
RuntimeMetadata is consumed by:
- Runtime
- Executor
- Verification
- ExecutionResult
