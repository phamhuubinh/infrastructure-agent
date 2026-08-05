# 02 - Current Architecture (Local, Today)
This describes the system **as it runs today**: single-user and single-machine, with a packaged Docker Compose runtime plus a source-development mode. The default installation exposes only local HTTP ports; outbound calls go to targets/Grafana/Zabbix/LLM/Internet APIs.
## Runtime shape
```
Installed runtime (install.sh + Docker Compose)
   ├── nginx reverse proxy     localhost:80
   ├── FastAPI                 localhost:61888
   ├── packaged SSR UI         internal port 3000
   ├── PostgreSQL              internal only
   └── RAG service             internal only

Host launcher (scripts/orion)
   ├── orion web   starts/attaches API + UI + proxy logs; Ctrl+C stops Web
   └── orion log   follows every Compose service; Ctrl+C only exits logs

Source development (src/cli/main.py)
   ├── local mode              runs the pipeline directly in-process
   └── python3 -m src.cli web  starts local FastAPI + Vite dev server
```
In local CLI mode, there is one process holding runtime state in memory. Targets are read from `targets.json` (`src/tool/target_store.py` / `target_registry.py`), while conversations persist in SQLite under `~/.orion/sessions.db`.

Target identity is explicit: the configured key `localhost` means the Orion
runtime environment. It is displayed as `orion-api` in the Compose install and
therefore describes the API container, not the physical Docker host. Physical
hosts must be registered as explicit SSH targets; no host namespace is mounted
implicitly.

In both Web runtimes, a FastAPI backend (`src/backend/api.py`) handles requests. Each chat session owns its conversation store, Agent instance, evidence cache, and execution lock. Source development uses SQLite at `~/.orion/sessions.db` by default; the Compose installation supplies PostgreSQL through `ORION_DATABASE_URL`. Optional API-key middleware is disabled by default in source development and enabled behind the local reverse proxy in the packaged stack.

Document analysis is a separate Web UI flow. A RAG project owns its documents, dense-vector collection, BM25 index, and analysis history under `RAG_DATA_DIR`. The API proxies `/api/rag/*` to the internal RAG service and passes the active model as request-scoped internal configuration. Chat never calls these endpoints and the Agent runtime refuses to register `knowledge_base` tools.
## Investigation pipeline (deterministic)
```
User Request
    ↓
Normalizer             (src/pipeline/normalizer.py — semantic, language-only)
    ↓
Parameter Extractor    (src/pipeline/parameter_extractor.py — service_name, port, process, path, time_range)
    ↓
Answer Type Classifier (src/pipeline/answer_type.py — Fact/List/Table/Chart/Assessment/Comparison)
    ↓
Target Resolution      (src/pipeline/target_resolver.py, src/tool/target_registry.py)
    ↓
Tool Selector          (src/pipeline/tool_selector.py — Linux/Grafana/Zabbix/Internet routing)
    ↓
Capability Planner     (src/pipeline/capability_planner.py — concept+action → capability plan)
    ↓
Execution Engine       (src/pipeline/execution_engine.py, execution_runtime.py, execution_graph.py)
    ├── Evidence Cache  (src/pipeline/evidence_cache.py — per-session, TTL 60s)
    ↓  calls
KnowledgeTool           (src/tool/knowledge_tool.py — single entry point into Child Tools)
    ├── mandatory read-only / parameter / target inspector chain
    ├── target preflight + capability precondition validation
    ↓  dispatches to
Child Tools: LinuxTool (SSH) / GrafanaTool / ZabbixTool / InternetTool
    ↓
Evidence Merge         (src/pipeline/evidence_merge.py, evidence_package.py, evidence_completeness.py)
    ↓
Evidence Correlation   (src/pipeline/evidence_correlation.py)
    ↓
Assessment (Agent)     (src/agent/deterministic_agent.py)
    ├── DeterministicResponder.try_response() — skip LLM for simple facts/lists/tables
    ├── ThresholdEvaluator (src/pipeline/threshold_evaluator.py — ok/info/warning/critical)
    ├── TimeRangeResolver (src/pipeline/time_range_resolver.py)
    └── AssessmentAdapter → AssessmentRequest → LLM → tool links
    ↓
Response
```
Every step above "Assessment (Agent)" is deterministic code — no LLM call. The `DeterministicResponder` runs inside the agent layer after evidence merge, not inside the pipeline. See `05_EXECUTION_PIPELINE.md` for what each stage owns.
## Model layer
- `src/model/llm_client.py` — thin client to the LLM API.
- `src/model/assessment_model_adapter.py` — abstract adapter contract (`assess()` / `assess_raw()`); `NotImplementedError` on the base class is intentional — real behavior lives in subclasses.
- `src/model/llm_assessment_adapter.py` — real adapter that turns collected evidence into an assessment via the LLM.
- `src/model/mock_assessment_adapter.py` — deterministic stand-in used when no LLM call should happen (development/offline use).
- `src/model/unconfigured_adapter.py` — explicit setup-mode response when no model has been selected; model absence does not prevent startup.
- `src/model/config_store.py` — persistent registry of user-managed model connections shared by CLI, API, and Web Settings, including connection tests.
- `src/model/protocol/prompt_builder_v2.py` — builds the prompt sent to the model from the evidence package.
## Tool layer
- `src/tool/tool.py` — abstract `Tool` interface (`NotImplementedError` on base class is intentional).
- `src/tool/knowledge_tool.py` — the **only** entry point the pipeline calls; aggregates Child Tool capabilities, dispatches execution. Nothing else in the pipeline talks to a Child Tool directly.
- `src/tool/linux/` — SSH-based command execution against registered targets, via `src/tool/execution_backend.py`.
- `src/tool/grafana/` — Grafana HTTP API queries.
- `src/tool/zabbix/` — Zabbix API queries.
- `src/tool/internet_tool.py` — HTTP fetch with SSRF protection (private IP block + DNS resolution guard).
- `src/backend/routers/knowledge.py` and `src/tool/RAGTool/` — the only active RAG integration; it is not a Chat tool.
- `src/tool/target_registry.py` / `target_store.py` — local JSON-backed list of investigable targets (host, port, user, identity file path).
Credential handling for Grafana/Zabbix tokens: `tools.json` contains only safe registry metadata; deployment URLs/tokens live in `/etc/orion/tool-credentials.json` and are mounted into the API container. See `07_DEVELOPMENT_RULES.md` and `09_ARCHITECTURE_DECISIONS.md` for the rule and reasoning.
## Frontend
- `ui/` — TanStack Start (React) app. Talks only to the backend API. It supports model add/install/test/select/delete controls, API-key configuration, isolated Chat sessions, and isolated RAG projects. It remains single-user; there are no accounts.
## What is intentionally out of scope right now
- No externally managed database is required. Source mode defaults to SQLite; the Docker installer starts a bundled PostgreSQL service. The RAG service stores project metadata/indexes on its own volume.
- No authentication / accounts (optional `ORION_API_KEY` middleware available for API endpoint protection).
- No remote hosting.
- No multi-user accounts, remote deployment, or background job queue.
These are not bugs. They are the current, intentional boundary of the project. `03_PLATFORM_ARCHITECTURE.md` describes what replaces this boundary, and `04_ROADMAP.md` describes the order in which that happens.
