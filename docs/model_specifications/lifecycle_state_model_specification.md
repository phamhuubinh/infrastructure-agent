# Shared Model Specification

# Model: LifecycleState

---

# Purpose

LifecycleState represents the current lifecycle status of a single execution.

It is an immutable snapshot describing the execution lifecycle at a specific point in time.

---

# Fields

| Field     | Type                     | Description                             |
| --------- | ------------------------ | --------------------------------------- |
| state     | ExecutionState           | Current execution state                 |
| timestamp | float                    | Timestamp when this state became active |
| metadata  | dict[str, object] | None | Optional state metadata                 |

---

# Constraints

* Immutable.
* Frozen dataclass.
* Slots enabled.
* No business logic.
* No validation logic.
* No helper methods.

---

# Ownership

LifecycleState belongs to the Runtime layer but is shared across Runtime components.

It may be referenced by:

* LifecycleManager
* ResultCollector
* Runtime diagnostics

---

# Notes

LifecycleState represents only the current lifecycle snapshot.

Lifecycle transition history is represented separately by LifecycleTransition.
