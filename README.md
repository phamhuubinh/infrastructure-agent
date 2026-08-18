# Orion

Evidence-driven investigation with AI-powered semantic planning and assessment.

> **Current status:** local, single-operator. Chat sessions use isolated agents and SQLite by default; Docker Compose uses PostgreSQL. The Web UI also exposes project-isolated RAG analysis, separate from Chat. API-key middleware (`ORION_API_KEY`), CLI, Web UI, and Electron Desktop are included.

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
User Request + bounded session context
    ↓
Semantic Planner (AI) — typed advisory route/intent/target/source/freshness plan
    ↓
Deterministic Harness
    ├── read-only / target / source / freshness / compute validation
    ├── direct stable answer → no infrastructure collectors
    ├── deterministic calculator → reviewed compute contract
    ├── current public information / URL → bounded Internet verification
    └── infrastructure plan → typed capability binding
                              ↓
                      Execution Engine
                              ↓
                    KnowledgeTool → Child Tools
                 (Linux, Grafana, Zabbix, Internet)
                              ↓
                 Evidence Merge + Facts/Findings
                              ↓
              deterministic or bounded AI response
                              ↓
       hard postconditions → relevance check when needed
             → at most one bounded repair → sanitizer
                              ↓
                  Response + safe ExecutionTrace
```

Natural-language semantic planning is model-driven in normal CLI/Web runtime.
Investigation and execution authority remain deterministic: the model has no
direct command/tool API, and planner output must pass the harness before any
collector can run. Planner/model failure does not fall back to regex-first live
routing.

## Configuration

### Infrastructure tools (Zabbix, Grafana)

Infrastructure tool configuration is split by sensitivity:

- **`tools.json`** — tracked, non-secret tool registry included in the API image. Do not add URLs or tokens to it.
- **`/etc/orion/tool-credentials.json`** — system-wide deployment endpoints and credentials, outside the source checkout. It is mounted read-only into the API container.

Create `/etc/orion/tool-credentials.json` with this structure:

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

A template is available at `config/tool-credentials.example.json`.

On a new machine, securely copy an existing credential file to `/etc/orion/tool-credentials.json` before running `./install.sh` if you want to reuse it. The path is independent of the operating-system account and Git never carries it. If the file is absent, the installer automatically creates a private empty `{}` file, skips Grafana/Zabbix setup, and continues installing Orion. It then reports exactly which tool is missing `url` or `token`. After adding credentials, run `docker compose up -d --force-recreate api` so Compose remounts the secret.

### Internet fetch

The `InternetTool` provides bounded public search and URL fetch with built-in SSRF protection. A harness-validated semantic plan that requires current public information or an explicit URL is forced through this deterministic verification path. Query-based verification requires a configured search provider; direct public-URL fetch works independently. A failed verification is returned as unverified/unknown rather than answered from stale model memory.

## Quick Start

### Complete application install

Docker Engine with Docker Compose is the only platform prerequisite. The installer creates the private Orion runtime secrets, initializes the system-wide Grafana/Zabbix credential file when needed, reports missing tool credentials, and starts the complete Orion application: Web UI, API, PostgreSQL, RAG service, and reverse proxy. Grafana/Zabbix setup may be skipped. Model runtimes and model weights are managed separately by the user and are not installed by Orion:

```bash
./install.sh
# → http://localhost
# → `orion help` is available from the host shell
```

The installer asks whether to skip model setup or connect an existing OpenAI-compatible endpoint. Skipping is valid: Orion still installs and starts. Model-dependent Chat requests return a clear setup-required response without dispatching guessed live tools, while deterministic hard-safety/model-management paths remain available; RAG analysis also reports that a model must be configured. A user-managed endpoint can be added later in **Cài đặt → Kết nối model** or through the CLI:

```bash
docker compose exec api orion model list
docker compose exec api orion model add primary \
  --base-url https://api.openai.com/v1 \
  --model gpt-4.1 --api-key-stdin
docker compose exec api orion model test primary
```

The CLI and Web settings connect to OpenAI-compatible, Ollama, or vLLM endpoints, but Orion does not install or manage those runtimes or their model weights. The runtime also accepts manually configured Anthropic connections for Chat; RAG synthesis requires an OpenAI-compatible connection.
In the Docker installation, loopback model URLs such as `http://localhost:11434` are mapped to the host automatically.

### Uninstall

```bash
./uninstall.sh              # confirm, then completely remove Orion and its data
./uninstall.sh --yes        # same cleanup without an interactive confirmation
./uninstall.sh --dry-run    # show everything that would be removed
```

Uninstall always deletes Orion containers, project-built images, Docker volumes, model connections, sessions, RAG projects/documents, logs, `.env`, and the host launcher. Interactive uninstall asks separately whether `/etc/orion/tool-credentials.json` should also be removed; answer `n` to keep the shared Grafana/Zabbix credentials. `--yes` preserves that file automatically. The source directory and model runtimes operated independently by the user are also preserved. The next `./install.sh` starts with new volumes, new runtime secrets, no model, and no sessions while reusing the monitoring credentials when retained.

### CLI

```bash
orion help
orion run
orion web       # start Web UI, show Web logs; Ctrl+C stops Web
orion log       # show logs from every Orion service
orion model list
```

The host command is a lightweight Docker launcher; it does not install Python packages or a virtual environment on the host. In the packaged installation, `orion web` starts the Web services when needed, opens `http://localhost`, and follows only API/UI logs generated from that invocation onward. Pressing `Ctrl+C` stops those Web services. `orion log` follows logs from every Compose service; pressing `Ctrl+C` there only exits the log viewer and leaves Orion running. On SSH/headless systems, `orion web` prints the URL instead of opening a browser.

### Web UI

```bash
# Terminal 1: RAG service
cd src/tool/RAGTool
uv sync --group dev  # first run only
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080

# Terminal 2: backend + auto-started Vite frontend
cd ../../..
python3 -m src.cli web
# → http://localhost:5173
```

The **Phân tích tài liệu** page creates independent RAG projects, uploads each project's documents, and stores its own analysis history. It always uses the active Orion model for answer synthesis and has no retrieval-only mode. If no model is configured, the project and upload workflow remains available but analysis returns a clear setup-required error.

### Docker Compose

Use `./install.sh` for a complete first installation. Direct `docker compose up -d --build` remains available to operators who have already created `.env` and `/etc/orion/tool-credentials.json` (an empty `{}` is valid).

The RAG service is internal-only in the root Compose stack. Browser requests always pass through the authenticated API.

### Web UI (single command, development mode)

```bash
python3 -m src.cli web
# Backend API: http://localhost:61888
# Frontend: auto-starts Vite dev server at http://localhost:5173
```

This source-development command also owns both local processes: it stays attached to the terminal and `Ctrl+C` stops them. To work only on the frontend against an already-installed Docker backend, run `npm --prefix ui run dev` and open `http://localhost:5173`; the Vite proxy reads `ORION_API_KEY` from the ignored root `.env` server-side and does not expose it to browser code.

### Production build

The TanStack Start SSR frontend requires the Nitro runtime for production.
For local use, development mode is recommended:

```bash
python3 -m src.cli web
```

## Documentation

The `docs/` directory is the **Source of Truth** for architectural and design documentation.

`docs/ai/` is written for AI coding agents working in this repo (start at `docs/ai/00_BOOTSTRAP.md` for reading order and conflict priority). It covers:

- the implemented local architecture
- the deterministic execution pipeline and tool/capability design rules
- mandatory development rules
- `docs/ai/08_PROJECT_STATE.md` — the single source of truth for what is actually implemented right now; if any other doc disagrees with it, this file wins
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` — the ADR log

`docs/adr/` holds longer-form narrative architecture decision records referenced from `docs/ai/09_ARCHITECTURE_DECISIONS.md`.

Additional project references:

- `docs/api/` — API reference and generated OpenAPI schema
- `scripts/qa/` — manual end-to-end QA runners; generated output goes to `artifacts/qa/`
