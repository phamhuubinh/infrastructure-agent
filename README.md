# Orion

Infrastructure investigation platform with AI-powered assessment.

Evidence-driven investigation with AI-powered assessment.

> **Current status:** local, single-user. Optional PostgreSQL session store (`ORION_DATABASE_URL`), optional API key auth (`ORION_API_KEY`), CLI + Web UI + Desktop App. No accounts, no remote hosting. See `docs/ai/08_PROJECT_STATE.md` for what actually exists.
>
> **Long-term direction:** evolve into a shared AI Platform (Web UI + API + Auth + Agent + Dify + RAG + Document Service + PostgreSQL, reachable over HTTPS from a VM, plus a Desktop App using the same backend). See `docs/ai/03_PLATFORM_ARCHITECTURE.md` for the target architecture and `docs/ai/04_ROADMAP.md` for the work sequencing (WP1–WP5). Some platform capabilities (PostgreSQL session store, API key auth, Electron desktop) are partially implemented — check `08_PROJECT_STATE.md` for status.

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
Execution Runtime → KnowledgeTool → Child Tools (Linux, Grafana, Zabbix, Internet, KB)
    ↓
Evidence Collection
    ↓
Assessment (AI)
    ↓
Response
```

The investigation pipeline is fully deterministic.
AI is used only for assessment.

## Configuration

### Infrastructure tools (Zabbix, Grafana)

Tool credentials are managed via two files:

- **`tools.json`** — tool registry (committed to git, contains no secrets).
- **`config/secrets.local.json`** — actual credentials (NOT committed to git).

Create `config/secrets.local.json` with this structure:

```json
{
  "grafana": {
    "url": "http://your-grafana:3000",
    "token": "your-grafana-token"
  },
  "zabbix": {
    "url": "http://your-zabbix/zabbix",
    "token": "your-zabbix-token"
  }
}
```

A template is available at `config/secrets.local.example.json`.

### Internet fetch

The `InternetTool` fetches external URLs with built-in SSRF protection. It is opt-in per request — the pipeline never invokes it automatically.

> **⚠️ Security note:** The Grafana token was previously hardcoded in source code and pushed to git history. It should be considered compromised. Revoke/rotate the token on your Grafana server and update `config/secrets.local.json` when convenient.

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

## Autonomous Development Workflow

The `.workflow/` directory contains the autonomous development supervisor:

```
.workflow/
├── supervisor.sh       # Entry point — orchestrates the entire workflow
├── state.json          # Persistent backlog & session state
├── session.log         # Structured log of all iterations
├── progress_report.md  # Sprint history and progress summary
├── daemon.pid          # PID file for supervisor daemon
├── commands/           # Reusable task scripts
│   ├── run-tests.sh    # Run all tests
│   ├── lint.sh         # Run linter
│   ├── typecheck.sh    # Run type checker
│   └── benchmark.sh    # Run benchmarks
├── backups/            # State backup snapshots
└── README.md           # Full workflow documentation
```

Each task produces one atomic git commit, test results, lint/typecheck results, and an updated `state.json`. Use `./.workflow/supervisor.sh` to start the autonomous loop.
