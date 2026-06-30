# Runtime Behavior Specification
# Behavior: ResultDispatcher
---
# Scope
This specification defines the required behavior of ResultDispatcher.
It supplements the Runtime API Specification and the Runtime Component Specification.
If a conflict exists, the Runtime Architecture remains the source of truth.
---
# Purpose
ResultDispatcher dispatches immutable ExecutionResult objects.
ResultDispatcher performs no result assembly.
ResultDispatcher performs no lifecycle management.
---
# Dispatch
Dispatch shall:
1. receive one immutable ExecutionResult;
2. dispatch the immutable ExecutionResult to the specified dispatch target;
3. report whether dispatch succeeded.
Each ExecutionResult shall be dispatched at most once.
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
