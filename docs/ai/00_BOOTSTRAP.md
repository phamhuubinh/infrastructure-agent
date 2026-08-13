# 00 - Bootstrap

> Read this document first. Orion documentation describes the repository as it
> exists; it does not contain roadmaps, speculative architecture, or unfinished
> feature plans.

## Reading order

1. `07_DEVELOPMENT_RULES.md` — mandatory engineering rules.
2. `08_PROJECT_STATE.md` — concise inventory of the current implementation.
3. `02_CURRENT_ARCHITECTURE.md` — runtime and component boundaries.
4. `05_EXECUTION_PIPELINE.md` — deterministic request/evidence flow.
5. `06_TOOL_AND_CAPABILITY_DESIGN.md` — Child Tool contracts.
6. `01_VISION.md` — current product purpose and scope.
7. `09_ARCHITECTURE_DECISIONS.md` — decisions enforced by the implementation.

Read the relevant operator, API, testing, or tool document only when the task
touches that area.

## Source-of-truth order

When documentation conflicts with the repository, use this order:

1. Current source code, configuration, public schemas, and tests.
2. `07_DEVELOPMENT_RULES.md`.
3. `08_PROJECT_STATE.md`.
4. `09_ARCHITECTURE_DECISIONS.md` and accepted ADRs.
5. Other documentation.

Fix stale documentation in the same change. Do not preserve an incorrect claim
as historical context in an active architecture or status document.

## Current documentation policy

- Document only behavior, interfaces, deployment modes, and constraints that
  are verifiable in the repository.
- Do not add roadmap, backlog, milestone, horizon, proposed architecture, or
  “coming soon” sections.
- Do not list an unimplemented feature as though its design were approved.
- Git history and the changelog hold historical information; active docs stay
  focused on the current system.

## Current scope

Orion is a local, single-operator application. It provides a deterministic
infrastructure investigation pipeline, model-backed assessment, a separate
project RAG workflow, CLI, Web UI, FastAPI API, Docker Compose packaging, and
an Electron wrapper for the installed Web application. Source mode uses SQLite;
the Compose stack uses PostgreSQL. API-key middleware provides single-tenant
API protection, not user accounts.

## Document set

| File | Purpose |
|---|---|
| `00_BOOTSTRAP.md` | Reading order and documentation policy |
| `01_VISION.md` | Current product purpose and scope |
| `02_CURRENT_ARCHITECTURE.md` | Implemented runtime architecture |
| `05_EXECUTION_PIPELINE.md` | Implemented request and evidence pipeline |
| `06_TOOL_AND_CAPABILITY_DESIGN.md` | Implemented tool/capability contracts |
| `07_DEVELOPMENT_RULES.md` | Mandatory engineering rules |
| `08_PROJECT_STATE.md` | Current implementation inventory |
| `09_ARCHITECTURE_DECISIONS.md` | Active architecture decisions |
