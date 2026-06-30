# Tool API Specification
# Component: Tool
---
# Purpose
This document defines the public API contract for Tool implementations.
A Tool performs exactly one requested operation.
A Tool exposes only its execution interface.
Implementation details remain private.
---
# Public Operations
```text
execute(
    arguments: dict[str, object],
) -> ToolResult
```
No other public operations are defined.
---
# Inputs
The operation receives:
* execution arguments.
Input objects shall not be modified.
---
# Return Value
Returns one immutable `ToolResult`.
---
# Operation Semantics
## execute
Executes exactly one requested operation.
The operation shall:
1. validate required inputs;
2. perform one atomic operation;
3. return one `ToolResult`.
Execution behavior is defined by the Tool Behavior Specification.
---
# Error Contract
Input validation failures shall raise `ValueError`.
Execution failures shall be represented by `ToolResult`.
Normal execution failures shall not raise exceptions.
---
# Implementation Constraints
The implementation shall:
* perform one atomic operation;
* remain stateless;
* perform no planning;
* perform no reasoning;
* perform no Runtime management;
* use only shared models where applicable.
