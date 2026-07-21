# 02 - Current Architecture (Local, Today)
This describes the system **as it runs today**: local process, single user, optional PostgreSQL and API key auth, no network exposure other than outbound calls to targets/Grafana/Zabbix/LLM/Internet APIs.
## Runtime shape
```
CLI (src/cli/main.py)
   │
   ├── local mode:  runs the pipeline directly in-process
   └── --web mode:  starts a backend API process + Vite dev server (ui/)
                     for the TanStack Start / React frontend
```
In local CLI mode, there is one process holding all state in memory. Targets are read from `targets.json` (`src/tool/target_store.py` / `target_registry.py`). Nothing persists — closing the process loses conversation state.

In `--web` mode, a FastAPI backend (`src/backend/api.py`) handles requests. When `ORION_DATABASE_URL` is set, sessions and documents persist in PostgreSQL via `PostgresConversationStore`. When unset, it falls back to JSON file storage under `~/.orion/sessions/`. Optional `ORION_API_KEY` enables API key authentication.
## Investigation pipeline (deterministic)
```
User Request
    ↓
Intent Resolution      (src/pipeline/intent_resolver.py)
    ↓
Target Resolution      (src/pipeline/target_resolver.py, src/tool/target_registry.py)
    ↓
Evidence Planning      (src/pipeline/evidence_planner.py, evidence_requirement.py)
    ↓
Capability Resolution  (src/pipeline/capability_resolver.py, capability_router.py, capability_library.py)
    ↓
Execution Planning     (src/pipeline/execution_planner.py, execution_plan.py)
    ↓
Execution Graph        (src/pipeline/execution_graph.py)
    ↓
Execution Runtime      (src/pipeline/execution_runtime.py, execution_engine.py)
    ↓  calls
KnowledgeTool           (src/tool/knowledge_tool.py — single entry point into Child Tools)
    ↓  dispatches to
Child Tools: LinuxTool (SSH) / GrafanaTool / ZabbixTool / InternetTool / KnowledgeBaseTool
    ↓
Evidence Merge         (src/pipeline/evidence_merge.py, evidence_package.py, evidence_completeness.py)
    ↓
Assessment (Agent)     (src/agent/deterministic_agent.py)
    ├── DeterministicResponder.try_response() — skip LLM if evidence is simple
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
- `src/model/protocol/prompt_builder_v2.py` — builds the prompt sent to the model from the evidence package.
## Tool layer
- `src/tool/tool.py` — abstract `Tool` interface (`NotImplementedError` on base class is intentional).
- `src/tool/knowledge_tool.py` — the **only** entry point the pipeline calls; aggregates Child Tool capabilities, dispatches execution. Nothing else in the pipeline talks to a Child Tool directly.
- `src/tool/linux_tool.py` — SSH-based command execution against registered targets, via `src/tool/execution_backend.py`.
- `src/tool/grafana_tool.py` — Grafana HTTP API queries.
- `src/tool/zabbix_tool.py` — Zabbix API queries.
- `src/tool/internet_tool.py` — HTTP fetch with SSRF protection (private IP block + DNS resolution guard).
- `src/tool/knowledge_base_tool.py` — RAG service proxy for health checks, document ingestion, and knowledge base queries.
- `src/tool/target_registry.py` / `target_store.py` — local JSON-backed list of investigable targets (host, port, user, identity file path).
Credential handling for Grafana/Zabbix tokens: see `07_DEVELOPMENT_RULES.md` and `09_ARCHITECTURE_DECISIONS.md` for the current rule and the reasoning — tokens must not be hardcoded in tool source files.
## Frontend
- `ui/` — TanStack Start (React) app. Talks to the local backend API started by `python -m src.cli --web`. No auth, no multi-user concept — it is a local dev-mode UI for one user on one machine.
## What is intentionally out of scope right now
- No database by default (state is in-memory + one local JSON file for targets; PostgreSQL available when `ORION_DATABASE_URL` is set — see WP4 migration in `08_PROJECT_STATE.md`).
- No authentication / accounts (optional `ORION_API_KEY` middleware available for API endpoint protection).
- No remote hosting.
- No automated tests, no benchmark runner — now resolved: **764 tests** (`tests/`) and a benchmark runner (`benchmark/`) both exist. See `08_PROJECT_STATE.md` for current status.
These are not bugs. They are the current, intentional boundary of the project. `03_PLATFORM_ARCHITECTURE.md` describes what replaces this boundary, and `04_ROADMAP.md` describes the order in which that happens.
