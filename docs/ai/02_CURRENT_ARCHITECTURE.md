# 02 - Current Architecture (Local, Today)
This describes the system **as it runs today**: local process, single user, no database, no auth, no network exposure other than outbound calls to targets/Grafana/Zabbix/LLM.
## Runtime shape
```
CLI (src/cli/main.py)
   │
   ├── local mode:  runs the pipeline directly in-process
   └── --web mode:  starts a backend API process + Vite dev server (ui/)
                     for the TanStack Start / React frontend
```
There is one process holding all state in memory for the duration of a run. Targets are read from a local JSON file (`src/tool/target_store.py` / `target_registry.py`). Nothing persists to a database. Closing the process loses conversation/job state — this is expected at the current stage.
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
Child Tools: LinuxTool (SSH) / GrafanaTool / ZabbixTool
    ↓
Evidence Collection     (src/pipeline/evidence_merge.py, evidence_package.py, evidence_completeness.py)
    ↓
Assessment (AI)          (src/pipeline/assessment_adapter.py → src/model/*)
    ↓
Response
```
Every step above the "Assessment (AI)" line is deterministic code — no LLM call. See `05_EXECUTION_PIPELINE.md` for what each stage owns.
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
- `src/tool/target_registry.py` / `target_store.py` — local JSON-backed list of investigable targets (host, port, user, identity file path).
Credential handling for Grafana/Zabbix tokens: see `07_DEVELOPMENT_RULES.md` and `09_ARCHITECTURE_DECISIONS.md` for the current rule and the reasoning — tokens must not be hardcoded in tool source files.
## Frontend
- `ui/` — TanStack Start (React) app. Talks to the local backend API started by `python -m src.cli --web`. No auth, no multi-user concept — it is a local dev-mode UI for one user on one machine.
## What is intentionally out of scope right now
- No database (state is in-memory + one local JSON file for targets).
- No authentication / accounts.
- No remote hosting, no HTTPS termination, no reverse proxy.
- No automated tests, no benchmark runner (`08_PROJECT_STATE.md` is explicit about this — do not assume otherwise). (Update: `tests/benchmark/` now exists.)
These are not bugs. They are the current, intentional boundary of the project. `03_PLATFORM_ARCHITECTURE.md` describes what replaces this boundary, and `04_ROADMAP.md` describes the order in which that happens.
