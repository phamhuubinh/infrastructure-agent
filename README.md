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

### API Server

```bash
pip install fastapi uvicorn
python api_server.py
# → http://localhost:8080
# POST /api/query  {"question": "check server health"}
# GET  /api/health
```

### Web UI (Lovable)

```bash
cd ui
npm install
npm run dev
# → http://localhost:5173
```

## Documentation

The `docs/` directory is the **Source of Truth** for architectural and design documentation.
