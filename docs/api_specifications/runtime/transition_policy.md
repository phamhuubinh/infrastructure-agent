# Runtime API Specification
# Component: TransitionPolicy
---
# Purpose
This document defines the public API contract for `TransitionPolicy`.
TransitionPolicy validates lifecycle transitions without modifying Runtime state.
---
# Public Operations
```text
can_transition(
    current_state: ExecutionState,
    requested_state: ExecutionState,
) -> bool
```
No other public operations are defined.
---
# Inputs
The operation receives:
* current execution state;
* requested execution state.
Inputs shall be treated as immutable.
---
# Return Value
Returns:
* `True` if the transition is permitted.
* `False` otherwise.
---
# Operation Semantics
## can_transition
Determines whether a transition from the current execution state to the requested execution state is permitted.
The operation performs validation only.
The supplied execution states shall not be modified.
---
# Error Contract
Invalid transitions are represented by `False`.
`TransitionPolicy` shall not raise exceptions for invalid transitions.
The caller is responsible for handling the validation result.
---
# Implementation Constraints
The implementation shall:
* remain stateless;
* contain no side effects;
* perform no lifecycle mutation;
* perform no timestamp handling;
* perform no history recording;
* use only shared execution models.
