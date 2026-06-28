# Runtime Behavior Specification
# Execution Result State Mapping
---
# Purpose
This document defines the relationship between terminal execution states and the resulting `ExecutionResult`.
---
# Result Mapping
| Execution State | Error                    | Output           |
| --------------- | ------------------------ | ---------------- |
| COMPLETED       | None                     | Execution output |
| FAILED          | Error message            | Optional         |
| CANCELLED       | Cancellation information | Optional         |
| TIMEOUT         | Timeout information      | Optional         |
---
# Constraints
Every execution produces exactly one `ExecutionResult`.
The execution state contained in `ExecutionResult` shall always be a terminal state.
`ExecutionResult` shall remain immutable after creation.
---
# Ownership
`ResultCollector` assembles `ExecutionResult`.
`ResultDispatcher` delivers `ExecutionResult`.
Neither component modifies an existing execution result.
