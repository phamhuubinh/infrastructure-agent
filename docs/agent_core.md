# Agent Core Architecture
---
# Purpose
Agent Core defines the high-level architecture of the Model-Driven Execution Runtime.
The architecture separates reasoning from execution.
The Reasoning Model owns all intelligence.
The Agent owns execution only.
Agent Core defines architectural responsibilities, ownership boundaries, and information flow.
Implementation details belong to individual component specifications.
---
# Scope
Agent Core defines:
* architectural responsibilities;
* component ownership;
* information flow;
* execution boundaries;
* reasoning boundaries.
Agent Core does not define:
* implementation details;
* runtime behavior;
* public APIs;
* data models;
* tool implementations.
---
# Core Components
The Agent Core consists of:
* Reasoning Model
* Agent
* Runtime
* Tool
Each component owns a single architectural responsibility.
---
# Component Responsibilities
## Reasoning Model
The Reasoning Model is the only intelligent component.
It is responsible for:
* reasoning;
* planning;
* decision making;
* information acquisition;
* observation interpretation;
* determining the next Action;
* producing the Final Response.
The Reasoning Model never performs execution.
---
## Agent
The Agent is an execution engine.
It is responsible for:
* receiving Actions;
* invoking Runtime execution;
* enforcing execution safety;
* collecting Observations;
* preserving execution outputs;
* returning raw Observations.
The Agent never:
* performs reasoning;
* performs planning;
* generates Actions;
* modifies Actions;
* interprets Observations;
* decides whether execution should continue.
---
## Runtime
The Runtime manages execution.
It is responsible for:
* execution lifecycle;
* execution environment;
* execution isolation;
* timeout management;
* cancellation;
* execution coordination.
The Runtime never performs reasoning or business logic.
---
## Tool
A Tool performs one atomic operation.
A Tool is responsible for:
* validating execution input;
* executing one deterministic operation;
* returning a structured execution result.
Tools never:
* perform reasoning;
* perform planning;
* collect additional information;
* invoke other Tools implicitly.
---
# Information Flow
The system follows an iterative Action → Observation loop.
```text
User
        │
            ▼
Reasoning Model
        │
            ▼
Action
        │
            ▼
Agent
        │
            ▼
Runtime
        │
            ▼
Tool
        │
            ▼
Observation
        │
            ▼
Reasoning Model
        │
   ┌────┴────┐
    ▼             ▼
Action   Final Response
```
Execution continues until the Reasoning Model produces a Final Response.
The Agent never determines when execution terminates.
---
# Architectural Boundaries
The following ownership boundaries shall always hold.
Reasoning belongs exclusively to the Reasoning Model.
Execution belongs to the Agent and Runtime.
Atomic operations belong to Tools.
Observations remain raw throughout execution.
Interpretation belongs exclusively to the Reasoning Model.
---
# Architectural Constraints
The following constraints shall always hold:
* The Reasoning Model is the only reasoning component.
* The Agent performs execution only.
* The Runtime manages execution only.
* Every Tool performs exactly one atomic operation.
* The Agent never modifies model-generated Actions.
* The Agent never modifies Observations.
* The Agent never performs implicit execution.
* Components communicate only through defined architectural contracts.
---
# Related Architecture Documents
Detailed architectural behavior is defined by:
* project_principles.md
* protocol/action_protocol.md
* runtime_architecture.md
* tool_architecture.md
* shared_architecture.md
Implementation details belong to the corresponding component specifications.
