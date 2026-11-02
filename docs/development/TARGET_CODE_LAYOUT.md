# Target code responsibilities

The redesign reuses the current module boundaries. This tree maps responsibilities;
it does not request directory renames or a rewrite.

```text
backend/src/
  orion/
    bootstrap/       # composition: one runtime, canonical registry, services
    contracts/       # provider-neutral identities including RuntimeScope
    access/          # application principal binding
    chat/            # runtime, bounded context, evidence and recovery
    models/          # ModelBackend and provider adapters
    tool_runtime/    # registry, validation, authorization and dispatch
    integrations/    # Internet, infrastructure and MCP clients
    knowledge/       # parsing, blob storage, retrieval and semantic indexing
    projects/        # Project lifecycle and knowledge ownership
    persistence/     # SQLite sessions/timeline/scheduler storage
    endpoints/       # device identity, gateway, tools and artifact metadata
    scheduler/       # schedule lifecycle and read-only runtime requests
    api/             # HTTP/SSE/WebSocket boundaries
    cli/             # Orion server/local commands
    security.py      # shared redaction/security helpers
    observability.py # safe diagnostics
  orion_endpoint/    # model-free worker protocol/executors/portable entry
worker/              # lightweight worker package and policy example
ui/                  # shared conversation UI, Projects, Remote Control
scripts/             # packaging, QA and platform checks
docs/                # target contracts and verified operations
```

## Dependency direction

```text
UI/API → application services → ChatRuntime
                                 ├── ContextBuilder / persistence
                                 ├── ModelBackend
                                 └── ToolRunner / canonical registry
                                          ├── KnowledgeService / integrations
                                          └── EndpointManager ← worker protocol
Scheduler → same ChatRuntime with read-only bound scope
```

Workers do not import a model runtime or choose application authority. Projects
and device sessions add scope rather than owning another ChatRuntime. A future
skill loader supplies trusted bounded instructions into the existing context
path; it does not require an agent subsystem.

Preserve canonical contracts when reusing modules. Do not rename/delete a module
because a historical plan used the word agent. Source-level and behavioral checks
must justify any requested implementation change.
