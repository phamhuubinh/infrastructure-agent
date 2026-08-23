# Orion Documentation

This documentation defines the **accepted target architecture** for Orion.

Orion is a personal AI agent focused on two practical jobs:

1. work with project knowledge and documents so the model can help create, review, explain, and
   reason about project material;
2. investigate infrastructure, assess what is happening, and propose the best practical course of
   action.

The agent may also answer ordinary questions directly when no tool or project knowledge is needed.

## Core principles

Two rules govern the architecture:

> **The model owns language understanding, reasoning, and next-action proposals.**

> **The harness owns authority, validation, execution, evidence, limits, and completion.**

Natural-language text is never execution authority. A model can propose an action, but only a
validated structured action can run.

## Product model

Orion exposes one agent experience rather than separate semantic modes for infrastructure, Internet,
RAG, or calculation. The accepted design lets the model choose whichever registered capability is
useful for the current request.

Current/target capability families include:

- Linux / SSH
- Grafana
- Zabbix
- Project knowledge / RAG
- Internet search and fetch
- Calculator

Future capability families should be addable without changing the agent's semantic core.

## Permission model

Orion has two effect classes:

- **READ** — observe or retrieve data without changing external state.
- **WRITE** — create, modify, delete, restart, deploy, or otherwise change state.

READ actions can run automatically. WRITE authority depends on the configured autonomy mode
(`READ`, `RW + ASK`, or `RW + FULL`).

## Projects

In the accepted target architecture, a Project is a workspace containing files/project knowledge and
multiple chats. Project knowledge is a normal READ capability available to chats in that Project;
it is not a separate reasoning architecture.

## Current implementation baseline

At commit `259f85b`, the configured Web/CLI Chat path uses the canonical model-driven agent runtime
and the superseded deterministic/semantic routing stack has been removed from that configured hot
path.

Not every accepted target item should be assumed to be implemented merely because it appears in
these documents. In particular, the current `src/tool/RAGTool/` service remains a standalone Web
Project/document-analysis workspace and is not registered as a Chat agent capability. That is an
implementation gap relative to ADR-0003, not a change to the accepted architecture.

Current implementation facts are established by source code, tests, generated API documentation,
and runtime evidence. If current code and an accepted ADR differ, document the gap and migrate the
implementation; do not silently redefine the ADR or resurrect legacy routing.

## Reading order

1. [PRODUCT.md](PRODUCT.md)
2. [architecture/OVERVIEW.md](architecture/OVERVIEW.md)
3. [architecture/AGENT_RUNTIME.md](architecture/AGENT_RUNTIME.md)
4. [architecture/CAPABILITIES.md](architecture/CAPABILITIES.md)
5. [architecture/PERMISSIONS.md](architecture/PERMISSIONS.md)
6. [architecture/PROJECTS_RAG_MEMORY.md](architecture/PROJECTS_RAG_MEMORY.md)
7. [architecture/EVIDENCE.md](architecture/EVIDENCE.md)
8. [architecture/MODELS.md](architecture/MODELS.md)
9. [architecture/SECURITY.md](architecture/SECURITY.md)
10. [architecture/UI_UX.md](architecture/UI_UX.md)
11. [architecture/EVENTS_LOGS_UI.md](architecture/EVENTS_LOGS_UI.md)
12. [architecture/FAILURE_RECOVERY.md](architecture/FAILURE_RECOVERY.md)
13. [development/ENGINEERING_RULES.md](development/ENGINEERING_RULES.md)
14. [development/TARGET_CODE_LAYOUT.md](development/TARGET_CODE_LAYOUT.md)
15. [development/MIGRATION.md](development/MIGRATION.md)
16. [development/TESTING.md](development/TESTING.md)
17. [development/CLEANUP.md](development/CLEANUP.md)
18. [decisions/README.md](decisions/README.md)

## Source-of-truth order

For target architecture decisions:

1. accepted decisions in `docs/decisions/`;
2. architecture documents in `docs/architecture/`;
3. engineering rules in `docs/development/`;
4. product documents.

A superseding architecture change requires an explicit new decision. Historical changelog entries
and migration notes do not override accepted ADRs.

For implementation truth, inspect the relevant code/tests/generated artifacts/runtime trace. An
implementation gap does not grant permission to reintroduce an architecture that an ADR rejected.
