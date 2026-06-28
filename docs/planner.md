# Planner Architecture
---
# Purpose
Planner Architecture defines how the agent transforms knowledge into executable plans.
The Planner is responsible for selecting goals, generating candidate actions, producing execution plans, validating those plans, and adapting them as new knowledge becomes available.
Implementation details belong to component specifications.
---
# Responsibilities
Planner Architecture is responsible for:
* selecting goals;
* generating candidate actions;
* prioritizing actions;
* producing execution plans;
* validating plans;
* supporting replanning.
Planner Architecture must not:
* execute actions;
* manage Runtime state;
* perform low-level execution.
---
# Architectural Principles
The following principles shall always hold:
* Planner owns planning.
* Executor owns execution.
* Planning is independent of Runtime.
* Plans are derived from the Knowledge Model.
* Planning continuously adapts to new knowledge.
---
# Core Concepts
## Goal
A Goal represents the desired outcome produced from the current Knowledge Model.
Goals drive the planning process.
---
## Goal Queue
The Goal Queue maintains prioritized goals awaiting planning.
Priorities may change as the Knowledge Model evolves.
---
## Candidate Actions
Candidate Actions are possible approaches for achieving a Goal.
They are generated from:
* current knowledge;
* historical context;
* discovered anomalies;
* available capabilities.
---
## Prioritization
Prioritization evaluates Candidate Actions using:
* relevance;
* expected impact;
* risk;
* resource cost;
* execution constraints.
---
## Planning
Planning transforms prioritized Candidate Actions into an executable Plan.
Planning considers:
* dependencies;
* ordering;
* constraints;
* available capabilities.
---
## Plan Validation
Plan Validation verifies that a generated Plan is feasible according to the current Knowledge Model.
Invalid plans require replanning.
---
## Replanning
Replanning generates a revised Plan whenever:
* execution feedback invalidates assumptions;
* new observations change the environment;
* goals change;
* constraints change.
---
# Information Flow
```text
Knowledge Model
        ↓
Goal Selection
        ↓
Goal Queue
        ↓
Candidate Actions
        ↓
Prioritization
        ↓
Planning
        ↓
Plan Validation
        ↓
Plan
        ↓
Executor
        ↓
Execution Feedback
        ↓
Knowledge Model
```
Execution feedback may trigger replanning.
---
# Relationships
## Knowledge Model
The Knowledge Model provides:
* goals;
* entities;
* relationships;
* patterns;
* anomalies;
* historical context.
Planner never owns the Knowledge Model.
---
## Executor
Planner produces Plans.
Executor executes Plans.
Planner never performs execution.
---
## Discovery
Discovery continuously updates the Knowledge Model.
Planner adapts planning decisions based on newly discovered knowledge.
---
## Plan Architecture
Planner produces Plans that conform to the Plan Architecture.
Planner never executes or modifies completed Plans during execution.
---
# Architectural Constraints
The following constraints shall always hold:
* Planner owns planning only.
* Executor owns execution only.
* Knowledge Model is the single planning context.
* Planning never depends on Tool implementations.
* Replanning is driven by evidence.
* Components communicate only through defined architectural contracts.
