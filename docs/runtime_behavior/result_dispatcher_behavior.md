# Runtime Behavior Specification
# Behavior: ResultDispatcher
---
# Scope
This specification defines the required behavior of ResultDispatcher.
It supplements the Runtime API Specification and the Runtime Component Specification.
If a conflict exists, the Runtime Architecture remains the source of truth.
---
# Purpose
ResultDispatcher delivers immutable execution results.
ResultDispatcher performs no result assembly.
ResultDispatcher performs no lifecycle management.
---
# Dispatch
Dispatch shall:
1. receive one immutable ExecutionResult;
2. deliver the execution result to the specified dispatch target;
3. report whether dispatch succeeded.
Each execution result shall be dispatched at most once.
Dispatch shall be deterministic.
---
# State Ownership
ResultDispatcher owns only temporary dispatch state.
Temporary dispatch state shall be released immediately after dispatch completes.
Execution results shall never be retained by ResultDispatcher.
---
# Failure Handling
If dispatch fails:
- the supplied ExecutionResult shall remain unchanged;
- dispatch failure shall be reported.
Dispatch failures shall not modify execution state.
