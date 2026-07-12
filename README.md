# Infrastructure Investigation Agent

A deterministic infrastructure investigation platform.

Evidence-driven investigation with AI-powered assessment.

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
