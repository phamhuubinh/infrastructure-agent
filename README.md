# Orion

Orion is a **local-first AI technical workbench** for technical work.

The primary interface is conversation. Users chat normally; Orion gives the configured model access to every registered tool automatically. There is no per-chat tool picker and no requirement for the user to decide whether RAG, Internet, Linux, Grafana, Zabbix, calculator, or another registered tool should be used.

A **Project** uses the same Chat/runtime and the same automatic tool system, while adding persistent project metadata and a project-scoped knowledge/RAG source.

## Product shape

```text
Chat
  = conversation
  + session context
  + attachments
  + all registered tools

Project
  = Chat
  + active project metadata
  + persistent project documents
  + project-scoped RAG source
```

The model makes semantic decisions:

```text
answer directly
or
use one or more registered tools
or
retrieve documents
or
combine several sources
```

Orion owns deterministic application behavior:

```text
assemble context
→ bind session/project runtime scope
→ provide all registered tool definitions
→ validate/dispatch model tool calls
→ normalize ToolResult
→ return results to the same model
→ persist public conversation state
```

There is intentionally **no semantic pre-router** that classifies the user's prompt into "RAG", "Internet", "Linux", or another intent before the model sees it.

## Current M1 tool family

The current executable slice provides deterministic calculation. Knowledge/RAG,
Internet, Linux, Grafana, and Zabbix are planned milestones and are not registered yet.

The target architecture keeps configured/registered tools available automatically to the model. A tool is configured at the application/integration level, not manually selected for each message.

## Start here

Read:

1. [`docs/PRODUCT.md`](docs/PRODUCT.md)
2. [`docs/architecture/OVERVIEW.md`](docs/architecture/OVERVIEW.md)
3. [`docs/architecture/CONTRACTS.md`](docs/architecture/CONTRACTS.md)
4. [`docs/architecture/MODEL_TOOL_LOOP.md`](docs/architecture/MODEL_TOOL_LOOP.md)
5. [`docs/architecture/PROJECT_RUNTIME.md`](docs/architecture/PROJECT_RUNTIME.md)
6. [`docs/architecture/RAG_AND_PROJECT_KNOWLEDGE.md`](docs/architecture/RAG_AND_PROJECT_KNOWLEDGE.md)
7. [`docs/operations/INSTALLATION.md`](docs/operations/INSTALLATION.md)

## Install and run the current repository

```bash
./install.sh
orion
```

This starts the packaged UI and API at `http://127.0.0.1:61888/`; the browser opens once
Orion is ready.

Useful commands:

```bash
orion log
orion help
make test
make lint
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) and [`docs/operations/`](docs/operations/).

## Documentation authority

The architecture/product `docs/` tree describes the **target product and architecture**. Existing source code is implementation state, not architectural authority.

Operations pages that describe current commands, ports, Compose services, or installer behavior must match the current repository implementation.

Reading these docs does not itself authorize code changes, migrations, commits, or repository operations.
