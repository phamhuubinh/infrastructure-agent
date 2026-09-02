# Orion

Orion is a **local-first AI technical workbench** for technical work.

The primary interface is conversation. Users chat normally; Orion gives the configured model access to every registered/configured tool automatically. There is no per-chat tool picker and no requirement for the user to decide whether RAG, Internet, Linux, Grafana, Zabbix, calculator, or another registered tool should be used.

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
→ expose the registry-derived discovery control plus request-local selected schemas
→ validate/dispatch model tool calls against the canonical registry
→ normalize ToolResult
→ return results to the same model
→ persist public conversation state
```

There is intentionally **no semantic pre-router** that classifies the user's prompt into "RAG", "Internet", "Linux", or another intent before the model sees it.

## Current tool families

The current executable registry includes calculator, Knowledge/RAG, and Internet tools. Linux, Grafana, and Zabbix tool families are registered when their infrastructure targets are configured.

Tool availability is registry-derived. To avoid resending every full tool schema on every model turn, Orion uses the ADR 0007 registry-derived progressive model-facing exposure protocol: `orion.tools.expand` accepts exact registered names from the canonical catalog and exposes those full schemas for the current request. This does not create a second registry, semantic tool picker, or authorization path; validation, runtime scope, and execution still use the canonical registry.

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

This starts the packaged UI and API at `http://127.0.0.1:61888/`; the browser opens once Orion is ready.

Useful commands:

```bash
orion log
orion help
make test
make lint
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) and [`docs/operations/`](docs/operations/).

## Documentation authority

The architecture/product `docs/` tree describes the **target product and architecture**. Accepted ADRs in `docs/decisions/` have the highest documentation authority. Existing source code and tests are implementation evidence and should remain aligned with those decisions.

Operations pages that describe current commands, ports, services, or installer behavior must match the current repository implementation.

Reading these docs does not itself authorize code changes, migrations, commits, or repository operations.
