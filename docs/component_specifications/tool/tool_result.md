# Tool Component Specification
# Component: ToolResult
---
# Purpose
This document specifies the ToolResult component.
ToolResult represents the immutable outcome of a single Tool execution.
ToolResult contains execution information only.
---
# Responsibilities
ToolResult is responsible for:
* representing execution outcomes;
* exposing execution outputs;
* exposing execution errors;
* preserving execution immutability.
ToolResult shall never:
* perform execution;
* perform reasoning;
* perform planning;
* modify execution state.
---
# Ownership
ToolResult owns:
* execution output;
* execution error information;
* execution status.
ToolResult never owns:
* Runtime lifecycle;
* Tool execution;
* execution scheduling;
* execution resources.
---
# Contents
A ToolResult may contain:
* execution status;
* output data;
* error information;
* implementation-specific metadata.
The exact model definition belongs to the shared execution models.
---
# Relationships
## Tool
A Tool produces one ToolResult.
---
## Runtime
Runtime receives ToolResult from the Tool.
Runtime does not modify ToolResult.
---
## Agent
The Agent receives execution observations through the Runtime.
The Agent does not modify ToolResult.
---
# State
ToolResult is immutable.
Once created, ToolResult shall never change.
---
# Constraints
ToolResult shall:
* represent exactly one Tool execution;
* remain immutable;
* contain no execution behavior;
* contain no reasoning behavior;
* communicate only through defined architectural contracts.
