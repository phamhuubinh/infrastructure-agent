# Runtime Behavior Specification
# Execution State Transition Table
---
# Purpose
This document defines the allowed execution lifecycle transitions used by the Runtime.
Transition rules are authoritative and shall be implemented only by `TransitionPolicy`.
---
# Allowed Transitions
| Current State | Allowed Next State |
| ------------- | ------------------ |
| CREATED       | READY              |
| READY         | RUNNING            |
| RUNNING       | COMPLETED          |
| RUNNING       | FAILED             |
| RUNNING       | CANCELLED          |
| RUNNING       | TIMEOUT            |
---
# Terminal States
The following execution states are terminal:
* COMPLETED
* FAILED
* CANCELLED
* TIMEOUT
Terminal states shall not transition to any other state.
---
# Invalid Transitions
Any transition not listed in the allowed transition table is invalid.
Invalid transitions shall not modify the current execution state.
---
# Ownership
Transition validation is performed exclusively by `TransitionPolicy`.
`LifecycleManager` applies only validated transitions.
