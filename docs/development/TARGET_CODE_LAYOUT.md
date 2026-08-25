# Target code layout

This is a clean target layout, not a requirement to preserve current module names.

```text
backend/
  pyproject.toml
  src/orion/
    bootstrap/       # application composition root
    contracts/       # provider-neutral canonical contracts
    access/          # local/authenticated principal adapters
    chat/            # one ChatRuntime and context assembly
    models/          # backend contracts and provider adapters
    tool_runtime/    # registry, validation, dispatch, tool handlers
    integrations/    # configured external clients when introduced
    persistence/     # stores and public timeline mapping
    api/             # HTTP/SSE boundary adapters
    observability/   # safe runtime diagnostics when introduced
    security/        # cross-cutting security helpers when introduced
    cli/             # local command surface
  tests/

ui/
```

## Dependency direction

```text
UI/API
  ↓
ChatRuntime
  ├── ContextBuilder
  ├── ModelBackend
  ├── ToolRegistry/ToolRunner
  ├── Session/Project stores
  └── Knowledge service
```

Tools depend on their integrations, not on semantic routers.

Project uses ChatRuntime rather than owning a second runtime.

## Migration rule

Current code can be reused if it cleanly implements one of these responsibilities. Old routing/protocol abstractions should not be preserved solely to reduce diff size.
