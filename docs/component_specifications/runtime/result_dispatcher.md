# Runtime Component Specification
# Component: ResultDispatcher
---
# Purpose
ResultDispatcher dispatches immutable ExecutionResult objects to their designated consumers.
It is the only Runtime component responsible for result dispatch.
ResultDispatcher never modifies execution results.
---
# Responsibilities
ResultDispatcher is responsible for:
* dispatching completed ExecutionResult objects;
* delivering ExecutionResult objects to registered consumers;
* reporting dispatch failures.
ResultDispatcher must not:
* execute Tools;
* manage lifecycle transitions;
* assemble execution results;
* modify execution results;
* perform planning;
* perform reasoning.
---
# Ownership
ResultDispatcher owns:
* result dispatch;
* dispatch coordination.
ResultDispatcher does not own:
* execution lifecycle;
* execution environment;
* execution result creation;
* execution scheduling.
---
# Dependencies
ResultDispatcher depends only on the shared models required for result dispatch.
Required models include:
* ExecutionResult
---
# Inputs
ResultDispatcher receives:
* execution reference;
* immutable `ExecutionResult`;
* dispatch target.
---
# Outputs
ResultDispatcher provides:
* dispatch confirmation; or
* dispatch failure information.
---
# State
ResultDispatcher maintains only temporary dispatch state.
Execution results shall not be retained after dispatch unless required by the Runtime Architecture.
---
# Constraints
ResultDispatcher shall:
* dispatch each `ExecutionResult` at most once;
* preserve `ExecutionResult` immutability;
* perform deterministic dispatch;
* perform no lifecycle management;
* perform no business logic;
* perform no planning.
---
# Relationships
## ResultCollector
ResultCollector assembles `ExecutionResult`.
ResultDispatcher delivers the completed result.
---
## Agent
Agent receives dispatched ExecutionResult objects.
---
# Failure Handling
Dispatch failures shall be reported to the Runtime.
`ExecutionResult` shall remain unchanged regardless of the dispatch outcome.
