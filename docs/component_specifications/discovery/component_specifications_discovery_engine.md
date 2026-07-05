# Discovery Engine Component Specification
---
# Purpose
Discovery Engine coordinates the discovery process.
It receives observations, transforms them into structured knowledge through the defined discovery workflow, and submits structured knowledge updates through the defined architectural contracts.
Discovery Engine never performs planning, reasoning, execution, or runtime management.
---
# Responsibilities
Discovery Engine is responsible for:
* coordinating discovery activities;
* accepting observations;
* initiating knowledge construction;
* submitting structured knowledge updates through defined architectural contracts;
* maintaining the discovery workflow.
Discovery Engine must never:
* perform planning;
* generate hypotheses;
* execute tools;
* modify Runtime state;
* select capabilities;
* make autonomous decisions.
---
# Inputs
Discovery Engine accepts:
* observations;
* discovery configuration;
---
# Outputs
Discovery Engine produces:
* structured knowledge updates;
* discovery status;
* discovery diagnostics.
Discovery Engine never returns planning decisions.
---
# Dependencies
Discovery Engine depends on architectural contracts only.
Allowed dependencies:
* Knowledge Model
* Shared Models
Discovery Engine must not directly depend on:
* Planner
* Runtime
* Capability
* Tool
* Executor
---
# Lifecycle
The Discovery Engine lifecycle consists of:
1. Receive observations.
2. Validate observations.
3. Start discovery workflow.
4. Construct structured knowledge.
5. Submit structured knowledge updates.
6. Finish discovery cycle.
---
# Error Handling
Discovery Engine reports discovery failures.
Discovery Engine never performs recovery planning.
Discovery Engine never retries execution.
---
# State
Discovery Engine should remain stateless whenever possible.
Persistent knowledge belongs exclusively to the Knowledge Model.
---
# Architectural Constraints
The following constraints always apply:
* Discovery Engine performs no reasoning.
* Discovery Engine performs no planning.
* Discovery Engine performs no execution.
* Discovery Engine never owns knowledge persistence.
* Discovery Engine communicates only through defined architectural contracts.
