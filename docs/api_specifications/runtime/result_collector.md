# Runtime API Specification
# Component: ResultCollector
---
# Purpose
ResultCollector provides the public interface for assembling one immutable ExecutionResult.
It exposes only result collection operations.
---
# Public Operations
## collect
Collect execution output, execution errors, and runtime metadata.
Return one immutable ExecutionResult.
---
# Operation Semantics
The runtime behavior of all operations is defined by the Runtime Behavior Specification.
---
# Error Contract
Result assembly failures shall raise ValueError.
No partial ExecutionResult shall be returned.
No operation shall expose mutable internal aggregation state.
