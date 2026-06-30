# Tool API Specification
# Component: ToolRegistry
---
# Purpose
This document defines the public API contract for `ToolRegistry`.
ToolRegistry manages Tool registration and Tool lookup.
ToolRegistry never executes Tools.
---
# Public Operations
```text
register(
    tool_id: str,
    tool: object,
) -> None
get(
    tool_id: str,
) -> Tool
```
No other public operations are defined.
---
# Inputs
Operations may receive:
* Tool identity;
* Tool instance.
Input objects shall not be modified.
---
# Return Value
Operations return:
* `None`;
* `Tool`;
depending on the invoked operation.
Returned Tool instances shall not be modified by ToolRegistry.
---
# Operation Semantics
The runtime behavior of all operations is defined by the Tool Behavior Specification.
## register
Registers one Tool using a unique Tool identity.
Duplicate Tool identities shall raise `ValueError`.
---
## get
Returns the Tool registered for the supplied Tool identity.
Unknown Tool identities shall raise `KeyError`.
---
# Error Contract
Duplicate Tool identities shall raise `ValueError`.
Unknown Tool identities shall raise `KeyError`.
Failed operations shall not partially modify registry state.
---
# Implementation Constraints
The implementation shall:
* perform Tool registration only;
* perform Tool lookup only;
* perform no Tool execution;
* perform no Runtime management;
* perform no planning;
* perform no reasoning.
