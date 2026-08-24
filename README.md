# Orion

Orion is a **local-first AI technical workbench** for technical work.

The primary interface is conversation. Users chat normally; Orion gives the configured model access to every registered tool automatically. There is no per-chat tool picker and no requirement for the user to decide whether RAG, Internet, Linux, Grafana, Zabbix, calculator, or another registered tool should be used.

A **Project** uses the same chat/runtime and the same automatic tool system, while adding a persistent project-scoped knowledge source for documents and project context.

## Product shape

```text
Chat
  = conversation + session context + attachments + all registered tools

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
use one or more tools
or
retrieve documents
or
combine several sources
```

Orion performs deterministic orchestration:

```text
assemble context
→ expose all registered tools
→ execute model tool calls
→ normalize tool results
→ return results to the model
→ persist public conversation state
```

There is intentionally **no semantic pre-router** that tries to classify the user's prompt into "RAG", "Internet", "Linux", or another intent before the model sees it.

## Current tool families

The repository currently contains implementations for:

- Knowledge / RAG;
- deterministic calculation;
- Internet;
- Linux;
- Grafana;
- Zabbix.

The target architecture keeps these available automatically to the model. A tool is configured at the application/integration level, not manually selected for each message.

## Start here

Read:

1. [`docs/PRODUCT.md`](docs/PRODUCT.md)
2. [`docs/architecture/OVERVIEW.md`](docs/architecture/OVERVIEW.md)
3. [`docs/architecture/MODEL_TOOL_LOOP.md`](docs/architecture/MODEL_TOOL_LOOP.md)
4. [`docs/architecture/PROJECT_RUNTIME.md`](docs/architecture/PROJECT_RUNTIME.md)
5. [`docs/architecture/RAG_AND_PROJECT_KNOWLEDGE.md`](docs/architecture/RAG_AND_PROJECT_KNOWLEDGE.md)
6. [`docs/operations/INSTALLATION.md`](docs/operations/INSTALLATION.md)

## Install and run the current repository

```bash
./install.sh
orion web
```

Useful commands:

```bash
orion log
docker compose ps
docker compose logs -f
make test
make lint
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) and [`docs/operations/`](docs/operations/).

## Documentation authority

The `docs/` tree describes the **target product and architecture**. Existing source code is implementation state, not architectural authority. When current code differs from the target docs, the difference is an implementation gap unless a newer explicit decision changes the target.

Reading these docs does not itself authorize code changes, migrations, commits, or repository operations.
