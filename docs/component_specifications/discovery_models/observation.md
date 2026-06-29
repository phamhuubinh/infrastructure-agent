# Observation Model Specification
---
# Purpose
Observation represents a single piece of evidence collected from the environment.
Observation contains raw information only.
Observation never performs reasoning, interpretation, or planning.
---
# Responsibilities
Observation is responsible for:
* representing a single observation;
* carrying raw evidence;
* remaining immutable after creation.
Observation must never:
* contain planning decisions;
* contain reasoning results;
* modify itself after creation.
---
# Ownership
Observation belongs to the Discovery subsystem.
Observation may be consumed by the Discovery Engine.
---
# Lifecycle
1. Created from environment observations.
2. Passed to the Discovery Engine.
3. Used during one discovery cycle.
4. The Observation lifecycle ends after the discovery cycle unless retained by higher-level architectural policies.
---
# Architectural Constraints
Observation shall remain:
* immutable;
* deterministic;
* independent of Runtime;
* independent of Planner;
* independent of Knowledge Model.
