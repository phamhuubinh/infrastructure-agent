# Runtime Behavior Specification
# Behavior: LifecycleManager
---
# Scope
This specification defines the required behavior of LifecycleManager.
It complements the Runtime API Specification and the Runtime Component Specification.
If a conflict exists, the Runtime Architecture remains the source of truth.
---
# Purpose
This document defines the required runtime behavior of LifecycleManager.
It specifies the execution lifecycle behavior independently of the implementation.
---
# Initialization
When initialize() succeeds, LifecycleManager shall:
1. associate the execution reference with the lifecycle;
2. create the initial execution lifecycle in the CREATED state;
3. initialize an empty lifecycle transition history.
initialize() may only succeed once.
Subsequent calls shall raise ValueError.
---
# Transition Processing
For every requested lifecycle transition, LifecycleManager shall perform the following steps in order:
1. validate the requested transition using TransitionPolicy;
2. reject invalid transitions by raising ValueError;
3. create one LifecycleTransition with its transition timestamp;
4. append the transition to the lifecycle history;
5. update the current execution state;
6. return the resulting execution state.
---
# Failure Behavior
If transition validation fails:
* the current execution state shall remain unchanged;
* the lifecycle transition history shall remain unchanged;
* no partial state update shall occur;
* ValueError shall be raised.
---
# Lifecycle History
Lifecycle history:
* contains every successful lifecycle transition;
* never contains failed transitions;
* preserves chronological order;
* is immutable when exposed through the public API.
---
# Terminal States
Terminal execution states shall reject every subsequent transition.
LifecycleManager shall not modify the lifecycle after a terminal state has been reached.
---
# Validation Ownership
LifecycleManager delegates lifecycle transition validation exclusively to TransitionPolicy.
LifecycleManager shall not duplicate transition rules defined by TransitionPolicy.
