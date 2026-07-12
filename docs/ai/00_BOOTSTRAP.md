# 00 - Bootstrap
> Read this document first, every time. It defines how the rest of `docs/ai/` is organized and how conflicts are resolved.
## Reading order
1. `00_BOOTSTRAP.md` — this file
2. `07_DEVELOPMENT_RULES.md` — mandatory rules, highest priority after this file
3. `08_PROJECT_STATE.md` — what is actually true right now (source of truth for status)
4. `01_VISION.md` — why this exists, current scope vs long-term direction
5. `02_CURRENT_ARCHITECTURE.md` — how the system works today
6. `03_PLATFORM_ARCHITECTURE.md` — where the system is going (future, not yet built)
7. `04_ROADMAP.md` — the work packages that connect today to the future state
8. `05_EXECUTION_PIPELINE.md` — the deterministic investigation pipeline
9. `06_TOOL_AND_CAPABILITY_DESIGN.md` — how tools/capabilities are added
10. `09_ARCHITECTURE_DECISIONS.md` — permanent record of decisions and why
## Conflict priority
If two documents disagree, resolve in this order (highest wins):
1. `07_DEVELOPMENT_RULES.md`
2. `08_PROJECT_STATE.md`
3. `09_ARCHITECTURE_DECISIONS.md`
4. Everything else
`08_PROJECT_STATE.md` wins over vision/architecture docs specifically because vision and architecture describe *intent*, while project state describes *reality*. Never assume a feature exists because it is described in `01_VISION.md` or `03_PLATFORM_ARCHITECTURE.md` — check `08_PROJECT_STATE.md`.
## Scope note (read this)
This project currently runs **entirely local, single-user, no network exposure**. `03_PLATFORM_ARCHITECTURE.md` and `04_ROADMAP.md` describe a future multi-user, VM-hosted platform. That future state does not exist yet. Do not write code that assumes a database, authentication, or a remote API server unless `08_PROJECT_STATE.md` says that work package is done.
## Document set
| File | Purpose |
|---|---|
| 00_BOOTSTRAP.md | Reading order, conflict priority |
| 01_VISION.md | Why the project exists, current vs long-term scope |
| 02_CURRENT_ARCHITECTURE.md | Architecture as it exists today (local) |
| 03_PLATFORM_ARCHITECTURE.md | Target architecture (AI Platform, future) |
| 04_ROADMAP.md | WP1–WP5 work packages |
| 05_EXECUTION_PIPELINE.md | Deterministic investigation pipeline |
| 06_TOOL_AND_CAPABILITY_DESIGN.md | Tool/capability design rules |
| 07_DEVELOPMENT_RULES.md | Mandatory engineering rules |
| 08_PROJECT_STATE.md | Current implementation status (source of truth) |
| 09_ARCHITECTURE_DECISIONS.md | ADR log |
