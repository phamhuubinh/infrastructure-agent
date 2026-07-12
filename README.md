# Infrastructure Investigation Agent

A deterministic infrastructure investigation platform.

Evidence-driven investigation with AI-powered assessment.

> **Current status: local, single-user only.** Runs on one machine, no accounts, no database, no remote hosting. This is intentional for the current phase — see `docs/ai/08_PROJECT_STATE.md`.
>
> **Long-term direction:** evolve into a shared AI Platform (Web UI + API + Auth + Agent + Dify + RAG + Document Service + PostgreSQL, reachable over HTTPS from a VM, plus a Desktop App using the same backend). See `docs/ai/03_PLATFORM_ARCHITECTURE.md` for the target architecture and `docs/ai/04_ROADMAP.md` for how the work is sequenced (WP1–WP5). None of that is built yet.

## Architecture

```
User Request
    ↓
Intent Resolution (deterministic)
    ↓
Target Resolution (deterministic)
    ↓
Evidence Planning (deterministic)
    ↓
Capability Resolution (deterministic)
    ↓
Execution Planning (deterministic)
    ↓
Execution Graph (deterministic)
    ↓
Execution Runtime → KnowledgeTool → Child Tools
    ↓
Evidence Collection
    ↓
Assessment (AI)
    ↓
Response
```

The investigation pipeline is fully deterministic.
AI is used only for assessment.

## Quick Start

### CLI

```bash
python -m src.cli
```

### Web UI

```bash
# Terminal 1: backend
python -m src.cli --web

# Terminal 2: frontend (development)
cd ui
npm install
npm run dev
# → http://localhost:5173
```

### Web UI (single command, development mode)

```bash
python -m src.cli --web
# Backend API: http://localhost:61888
# Frontend: auto-starts Vite dev server at http://localhost:5173
```

### Production build

The TanStack Start SSR frontend requires the Nitro runtime for production.
For local use, development mode is recommended:

```bash
python -m src.cli --web
```

## Documentation

The `docs/` directory is the **Source of Truth** for architectural and design documentation.

`docs/ai/` is written for AI coding agents working in this repo (start at `docs/ai/00_BOOTSTRAP.md` for reading order and conflict priority). It covers:

- current architecture (local, today) vs. target platform architecture (future)
- the deterministic execution pipeline and tool/capability design rules
- mandatory development rules
- `docs/ai/08_PROJECT_STATE.md` — the single source of truth for what is actually implemented right now; if any other doc disagrees with it, this file wins
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` — the ADR log

`docs/adr/` holds longer-form narrative architecture decision records referenced from `docs/ai/09_ARCHITECTURE_DECISIONS.md`.
