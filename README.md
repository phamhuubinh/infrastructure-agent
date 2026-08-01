# Orion

Evidence-driven investigation with AI-powered assessment.

> **Current status:** local, single-user. Chat sessions use isolated agents and SQLite by default (optional PostgreSQL). The Web UI also exposes project-isolated RAG analysis; RAG is not part of the chat tool flow. Optional API key auth (`ORION_API_KEY`), CLI + Web UI + Desktop App. No accounts or remote hosting.
>
> **Long-term direction:** evolve into a shared AI Platform (Web UI + API + Auth + Agent + RAG + Document Service + PostgreSQL, reachable over HTTPS from a VM, plus a Desktop App using the same backend). See `docs/ai/03_PLATFORM_ARCHITECTURE.md` for the target architecture and `docs/ai/04_ROADMAP.md` for the work sequencing (WP1–WP5). Some platform capabilities (PostgreSQL session store, API key auth, Electron desktop) are partially implemented — check `08_PROJECT_STATE.md` for status.

## Architecture

```
Web UI
├── Chat session
│   ↓ /api/query
│   Per-session Agent + conversation store + evidence cache + lock
│   ↓
│   Infrastructure investigation pipeline
│
└── RAG project
    ↓ /api/rag/projects/{project_id}/...
    Project documents + dense index + BM25 index + analysis history
    ↓
    Dedicated RAG service
```

The two flows are deliberately isolated: chat cannot register or call the RAG tool, and one RAG project cannot retrieve another project's chunks.

The chat investigation flow is:

```
User Request
    ↓
Normalizer (deterministic) — semantic normalization (language-only)
    ↓
Parameter Extractor (deterministic) — service_name, port, time_range, process, path
    ↓
Answer Type Classifier (deterministic) — Fact/List/Table/Chart/Assessment/Comparison
    ↓
Target Resolution (deterministic) — hostname detection, fuzzy matching, aliases
    ↓
Tool Selector (deterministic) — Linux/Grafana/Zabbix/Internet routing
    ↓
Capability Planner (deterministic) — concept+action → capability plan
    ↓
Evidence Collection (deterministic)
    ├── Execution Engine → KnowledgeTool → Child Tools (Linux, Grafana, Zabbix, Internet)
    └── Evidence Cache (per-session, TTL 60s)
    ↓
Evidence Merge + Correlation (deterministic)
    ↓
Assessment Pipeline
    ├── Deterministic Responder (short-circuit for Fact/List/Table answers)
    ├── Threshold Evaluator (severity: ok/info/warning/critical)
    └── LLM Assessment (AI) → evidence interpretation + recommendations
    ↓
Response
```

The investigation pipeline is fully deterministic.
AI is used only for assessment.

## Configuration

### Infrastructure tools (Zabbix, Grafana)

Tool credentials are managed via two files:

- **`tools.json`** — local tool registry (gitignored because deployments may include private endpoints).
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

### Complete application install

Docker Engine with Docker Compose is the only platform prerequisite. The installer creates the private runtime secrets and starts the complete Orion application: Web UI, API, PostgreSQL, RAG service, and reverse proxy. Model runtimes and model weights are managed separately by the user and are not installed by Orion:

```bash
./install.sh
# → http://localhost
# → `orion help` is available from the host shell
```

The installer asks whether to skip model setup or connect an existing OpenAI-compatible endpoint. Skipping is valid: Orion still installs and starts, while Chat assessment and RAG analysis explain that a model must be configured. A user-managed endpoint can be added later in **Cài đặt → Kết nối model** or through the CLI:

```bash
docker compose exec api orion model list
docker compose exec api orion model add primary \
  --base-url https://api.openai.com/v1 \
  --model gpt-4.1 --api-key-stdin
docker compose exec api orion model test primary
```

Orion can connect to OpenAI-compatible, Ollama, or vLLM endpoints, but it does not install or manage those runtimes or their model weights.
In the Docker installation, loopback model URLs such as `http://localhost:11434` are mapped to the host automatically.

### Uninstall

```bash
./uninstall.sh              # remove the app, preserve persistent data
./uninstall.sh --purge      # also remove all Orion data and private configuration
```

Both modes preserve this source directory. Purge mode requires confirmation; use `--yes` only for non-interactive automation.

### CLI

```bash
orion help
orion run
orion web       # open the packaged Web UI in the default browser
orion model list
```

The host command is a lightweight launcher for the CLI inside the running API container; it does not install Python packages or a virtual environment on the host. In the packaged installation, `orion web` opens the already-running Web UI at `http://localhost` with the desktop's default browser. On SSH/headless systems it prints the URL instead of attempting to start a development Vite server inside the container.

### Web UI

```bash
# Terminal 1: RAG service
cd src/tool/RAGTool
pip install -r requirements.txt  # first run only
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080

# Terminal 2: backend + auto-started Vite frontend
cd ../../..
python3 -m src.cli web
# → http://localhost:5173
```

The **Phân tích tài liệu** page creates independent RAG projects, uploads each project's documents, and stores its own analysis history. It always uses the active Orion model for answer synthesis and has no retrieval-only mode. If no model is configured, the project and upload workflow remains available but analysis returns a clear setup-required error.

### Docker Compose

Use `./install.sh` for a complete first installation. Direct `docker compose up -d --build` remains available to operators who have already created `.env`.

The RAG service is internal-only in the root Compose stack. Browser requests always pass through the authenticated API.

### Web UI (single command, development mode)

```bash
python3 -m src.cli web
# Backend API: http://localhost:61888
# Frontend: auto-starts Vite dev server at http://localhost:5173
```

### Production build

The TanStack Start SSR frontend requires the Nitro runtime for production.
For local use, development mode is recommended:

```bash
python3 -m src.cli web
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

Additional project references:

- `docs/api/` — API reference and generated OpenAPI schema
- `docs/project/` — historical backlog and implementation plans
- `scripts/qa/` — manual end-to-end QA runners; generated output goes to `artifacts/qa/`
