# Discovery Engine API Specification
---
# Purpose
This document defines the public architectural contract of the Discovery Engine.
The API specifies the interaction between Discovery Engine and other architectural components.
Implementation details are intentionally excluded.
---
# Service
Discovery Engine exposes a single discovery service.
The service accepts observations and produces structured knowledge updates.
---
# Input
The Discovery Engine accepts:
* observations;
* discovery configuration (optional).
Observations represent raw evidence collected from the environment.
The Discovery Engine never accepts planning instructions.
---
# Output
The Discovery Engine produces:
* structured knowledge updates;
* discovery status;
* discovery diagnostics.
The Discovery Engine never produces execution plans.
---
# Side Effects
The Discovery Engine may submit structured knowledge updates to the Knowledge Model through architectural contracts.
The Discovery Engine never modifies Runtime state.
The Discovery Engine never executes tools.
---
# Error Handling
Discovery failures shall be reported through discovery diagnostics.
The Discovery Engine never retries discovery automatically.
The Discovery Engine never performs recovery planning.
---
# Preconditions
The supplied observations shall be valid according to the architectural contracts.
---
# Postconditions
The discovery cycle completes with either:
* successful knowledge updates; or
* discovery diagnostics describing the failure.
---
# Architectural Constraints
The Discovery Engine API shall remain:
* deterministic;
* stateless whenever possible;
* independent of Planner;
* independent of Runtime;
* independent of Capability;
* independent of Tool.
