# Runtime Behavior Specification
# Behavior: ResultCollector
---
# Scope
This specification defines the required behavior of ResultCollector.
It supplements the Runtime API Specification and the Runtime Component Specification.
If a conflict exists, the Runtime Architecture remains the source of truth.
---
# Purpose
ResultCollector assembles the immutable execution result for one execution.
ResultCollector performs no execution.
ResultCollector performs no lifecycle management.
---
# Collection
Result collection shall:
1. collect execution output;
2. collect execution errors;
3. collect runtime metadata;
4. assemble one immutable ExecutionResult;
5. return the assembled execution result.
Result collection shall be deterministic.
---
# Result Assembly
ExecutionResult shall contain only information produced during the execution.
ResultCollector shall never modify collected data after result assembly completes.
Exactly one ExecutionResult shall be produced for one execution.
---
# State Ownership
ResultCollector owns only temporary aggregation state.
Temporary aggregation state shall be released after result assembly completes.
ResultCollector shall not retain execution state after completion.
---
# Failure Handling
If result assembly fails:
- partial aggregation state shall be discarded;
- no partial ExecutionResult shall be returned.
Result consistency shall always be preserved.
