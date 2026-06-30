# Tool Component Specification
# Component: Tool
---
# Purpose
This document specifies the Tool component.
A Tool performs one atomic operation.
A Tool owns execution of the requested operation only.
Behavior is defined by the Tool Behavior Specification.
The public interface is defined by the Tool API Specification.
---
# Responsibilities
A Tool is responsible for:
* validating execution inputs;
* performing one atomic operation;
* producing one ToolResult;
* reporting execution failures.
A Tool shall never:
* perform reasoning;
* perform planning;
* perform execution orchestration;
* manage Runtime resources;
* invoke the Reasoning Model.
---
# Ownership
A Tool owns:
* execution logic;
* temporary execution state.
A Tool never owns:
* Runtime lifecycle;
* Runtime resources;
* execution scheduling;
* Action generation;
* Observation generation.
---
# Inputs
A Tool consumes:
* execution arguments.
Inputs shall be treated as immutable.
---
# Outputs
A Tool produces:
* one immutable ToolResult.
---
# Relationships
## Runtime
Runtime invokes the Tool.
Runtime manages execution.
---
## Shared
A Tool consumes shared execution models.
---
## Agent
A Tool never communicates directly with the Agent.
---
## Reasoning Model
A Tool never communicates directly with the Reasoning Model.
---
# State
A Tool is stateless.
Execution state exists only during execution.
No execution state shall be retained after completion.
---
# Constraints
A Tool shall:
* execute exactly one requested operation;
* remain deterministic;
* remain stateless;
* communicate only through defined architectural contracts.
