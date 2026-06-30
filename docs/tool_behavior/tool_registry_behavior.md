# Tool Behavior Specification
# Behavior: ToolRegistry
---
# Scope
This specification defines the required behavior of ToolRegistry.
It supplements the Tool API Specification and the Tool Component Specification.
If a conflict exists, the Tool Architecture remains the source of truth.
---
# Purpose
ToolRegistry manages Tool registration and lookup.
ToolRegistry performs no Tool execution.
ToolRegistry performs no Runtime management.
---
# Registration
Tool registration shall:
1. validate the Tool identity;
2. reject duplicate Tool identities;
3. register exactly one Tool instance for each Tool identity;
4. make the Tool available for lookup.
Registration shall be deterministic.
---
# Lookup
Tool lookup shall:
1. receive one Tool identity;
2. return the registered Tool instance;
3. raise `KeyError` if the Tool identity is unknown.
Lookup shall not modify registry state.
---
# State Ownership
ToolRegistry owns only the Tool registration mapping.
Registered Tool instances shall remain unchanged by ToolRegistry.
---
# Failure Handling
If registration fails:
- registry state shall remain unchanged;
- no partial registration shall occur.
If lookup fails:
- registry state shall remain unchanged;
- `KeyError` shall be raised.
