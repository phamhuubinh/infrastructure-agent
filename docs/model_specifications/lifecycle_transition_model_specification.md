# Shared Model Specification

# Model: LifecycleTransition

---

# Purpose

LifecycleTransition represents one immutable lifecycle transition between two execution states.

Each transition records how the lifecycle changed during execution.

---

# Fields

| Field      | Type                     | Description                  |
| ---------- | ------------------------ | ---------------------------- |
| from_state | ExecutionState           | Previous lifecycle state     |
| to_state   | ExecutionState           | New lifecycle state          |
| timestamp  | float                    | Transition timestamp         |
| metadata   | dict[str, object] | None | Optional transition metadata |

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

LifecycleTransition belongs to the Runtime layer but is shared across Runtime components.

It may be referenced by:

* LifecycleManager
* Runtime diagnostics

---

# Notes

LifecycleTransition records historical lifecycle changes.

It never represents the current lifecycle state.
