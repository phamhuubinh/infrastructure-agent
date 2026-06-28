# Agent Core Architecture
---
# Purpose
Agent Core defines the high-level architecture of the autonomous agent.
It specifies how the major architectural components collaborate to observe the environment, build knowledge, generate hypotheses, plan actions, execute work, and continuously improve the internal understanding of the system.
Agent Core defines responsibilities and interactions only.
Implementation details belong to individual component specifications.
---
# Core Components
The Agent Core consists of:
* Observation
* Knowledge Model
* Planner
* Executor
Hypothesis generation is part of the reasoning process built on top of the Knowledge Model.
---
# Responsibilities
Agent Core is responsible for:
* defining the overall reasoning cycle;
* defining component responsibilities;
* defining information flow between components;
* defining architectural boundaries.
Agent Core must not define:
* implementation details;
* public APIs;
* runtime behavior;
* data structures.
---
# Information Flow
The autonomous agent operates as a continuous reasoning loop.
```text
Observation
        ↓
Knowledge Model
        ↓
Hypothesis
        ↓
Planner
        ↓
Executor
        ↓
Observation
```
Each iteration updates the Knowledge Model, enabling continuous refinement of future decisions.
---
# Architectural Constraints
The following constraints shall always hold:
* Observation collects information without making decisions.
* Knowledge Model is the single source of internal knowledge.
* Planner makes planning decisions only.
* Executor performs execution only.
* Components communicate only through their defined architectural contracts.
* No component may assume responsibilities owned by another component.
---
# Related Architecture Documents
The detailed behavior of each component is defined separately:
* knowledge_model.md
* planner.md
* executor.md
* runtime_architecture.md
* shared_architecture.md
