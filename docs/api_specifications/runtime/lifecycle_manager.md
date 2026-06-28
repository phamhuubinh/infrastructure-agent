# Runtime API Specification
# Component: LifecycleManager
---
# Purpose
This document defines the public API contract for `LifecycleManager`.
LifecycleManager manages the lifecycle of a single execution.
---
# Public Operations
```text
initialize(execution_reference: str) -> None
transition(
    requested_state: ExecutionState,
    metadata: dict[str, object] | None = None,
) -> ExecutionState
get_state() -> ExecutionState
get_history() -> tuple[LifecycleTransition, ...]

is_terminal() -> bool
```
No other public operations are defined.
---
# Inputs
Operations may receive:
* execution reference;
* requested execution state;
* transition metadata.
Inputs shall not be modified.
---
# Return Value
Operations return:
* `ExecutionState`;
* `tuple[LifecycleTransition, ...]`;
* `bool`;
* `None`;
depending on the invoked operation.
Returned objects shall not expose mutable internal state.
---
# Operation Semantics
## initialize
Creates the initial execution lifecycle in the CREATED state.
May only be called once.
---
## transition
Attempts to transition to the requested execution state.
A successful transition shall be recorded in the lifecycle history.
Returns the resulting execution state after a successful transition.
Invalid transitions shall raise `ValueError`.
The current lifecycle state shall remain unchanged if the transition fails.
---
## get_state
Returns the current execution state.
The returned value shall not expose mutable internal state.
---
## get_history
Returns an immutable lifecycle transition history.
The returned history contains every successful lifecycle transition.
History is ordered chronologically from oldest to newest.
---
## is_terminal
Returns whether the current execution state is terminal.
---
# Error Contract
Invalid lifecycle transitions shall raise `ValueError`.
Failed operations shall not partially modify lifecycle state.
---
# Implementation Constraints
The implementation shall:
* use only the Python standard library and shared execution models;
* preserve the public API;
* avoid placeholder implementations;
* avoid TODO/FIXME markers;
* avoid unused imports;
* avoid introducing unspecified Runtime abstractions.
