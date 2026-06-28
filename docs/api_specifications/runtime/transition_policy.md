# Runtime API Specification

# Component: TransitionPolicy

---

# Purpose

This document defines the public API contract for TransitionPolicy.

TransitionPolicy determines whether a lifecycle transition is allowed.

It contains no Runtime state and performs no state mutation.

---

# Public Interface

TransitionPolicy exposes the following public operation.

```
can_transition(
    current_state: ExecutionState,
    requested_state: ExecutionState,
) -> bool
```

No other public operations are defined.

---

# Inputs

Required:

- current execution state;
- requested execution state.

Inputs must be immutable.

---

# Outputs

Returns:

- true if the transition is permitted;
- false otherwise.

TransitionPolicy never modifies execution state.

---

# Error Contract

TransitionPolicy does not raise exceptions for invalid transitions.

Invalid transitions are represented by:

```
False
```

The caller is responsible for handling the result.

---

# Stateless Behavior

TransitionPolicy maintains no internal Runtime state.

Repeated calls with identical inputs must always produce identical outputs.

---

# Implementation Constraints

The implementation shall:

- use only shared execution models;
- contain no Runtime state;
- contain no side effects;
- perform no lifecycle mutation;
- perform no timestamp handling;
- perform no history recording.

---

# Notes

LifecycleManager is responsible for acting on the validation result.

TransitionPolicy is responsible only for transition validation.

Runtime components must not duplicate transition validation logic.
