# Tool Component Specification
# Component: ToolRegistry
---
# Purpose
This document specifies the ToolRegistry component.
ToolRegistry owns Tool registration and Tool lookup.
Behavior is defined by the Tool Behavior Specification.
The public interface is defined by the Tool API Specification.
---
# Responsibilities
ToolRegistry is responsible for:
* registering Tool instances;
* maintaining Tool identity uniqueness;
* resolving Tool instances by identity.
ToolRegistry shall never:
* execute Tools;
* perform Runtime management;
* perform planning;
* perform reasoning;
* modify Tool implementations.
---
# Ownership
ToolRegistry owns:
* Tool registration mapping.
ToolRegistry never owns:
* Tool execution;
* Runtime lifecycle;
* Runtime resources;
* execution scheduling;
* ToolResult.
---
# Inputs
ToolRegistry consumes:
* Tool identity;
* Tool instance.
Inputs shall be treated as immutable.
---
# Outputs
ToolRegistry produces:
* Register produces no return value.
* Lookup returns one registered Tool instance.
---
# Relationships
## Tool
ToolRegistry stores Tool instances.
ToolRegistry never executes Tools.
---
## Runtime
Runtime may resolve Tools through ToolRegistry.
ToolRegistry does not manage Runtime execution.
---
## Shared
ToolRegistry may reference shared execution models through Tool implementations.
---
# State
ToolRegistry maintains registration state only.
Registration state persists until explicitly modified.
---
# Constraints
ToolRegistry shall:
* maintain unique Tool identities;
* preserve registration consistency;
* perform deterministic lookup;
* communicate only through defined architectural contracts.
