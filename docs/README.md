# Orion Documentation

This documentation defines the **target architecture** for the Orion refactor.
It replaces the previous narrative architecture documentation.

Orion is a personal AI agent focused on two practical jobs:

1. work with project knowledge and documents so the model can help create,
   review, explain, and reason about project material;
2. investigate infrastructure, assess what is happening, and propose the best
   practical course of action.

The agent may also answer ordinary questions directly when no tool or project
knowledge is needed.

## Core principles

Two rules govern the architecture:

> **The model owns language understanding, reasoning, and next-action proposals.**

> **The harness owns authority, validation, execution, evidence, limits, and completion.**

Natural-language text is never execution authority. A model can propose an
action, but only a validated structured action can run.

## Product model

Orion exposes one agent experience rather than separate chat, infrastructure,
Internet, and RAG modes. The model can use whichever registered capability is
useful for the current request.

Current capability families include:

- Linux / SSH
- Grafana
- Zabbix
- Project knowledge / RAG
- Internet search and fetch
- Calculator

Future capability families should be addable without changing the agent core.

## Permission model

Orion has only two effect classes:

- **READ** — observe or retrieve data without changing external state.
- **WRITE** — create, modify, delete, restart, deploy, or otherwise change state.

READ actions run without approval. WRITE actions use one of two autonomy modes:

- **ASK** — Orion asks before executing the declared write scope.
- **FULL** — Orion executes validated writes without asking.

The default safe mode should be READ.

## Projects

A Project behaves like a project workspace in a modern AI chat product:

- one Project has files / project knowledge;
- one Project can contain many chats;
- each chat has its own bounded conversation context;
- chats in the Project can retrieve from that Project's knowledge;
- Project knowledge is not a separate agent mode.

## Documentation status

These files describe the accepted target architecture. During the refactor the
codebase may temporarily lag this documentation. That is expected. The
migration is complete only when code, tests, generated API documentation, and
runtime behavior converge on this design.

Do not preserve legacy architecture merely because it already exists.

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

For current implementation facts during migration, source code and tests remain
factual evidence of what is implemented, but they do not override an accepted
architecture decision.
