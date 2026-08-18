# 02 - Current Architecture

This document describes the implemented local, single-operator system.

## Runtime shapes

```text
Installed runtime (install.sh + Docker Compose)
  Browser / Electron
          |
          v
  Nginx reverse proxy        127.0.0.1:80
       |              |
       v              v
  FastAPI API         TanStack Start SSR UI
       |              internal :3000
       +-------> PostgreSQL
       +-------> RAG service

Source runtime
  orion run                 in-process CLI + SQLite
  python3 -m src.cli web    FastAPI + Vite + SQLite
```

The installed launcher executes the CLI inside the API container. `orion web`
starts the Web services when needed, follows current API/UI logs, and stops
those Web services on `Ctrl+C`. `orion log` follows the whole Compose stack and
does not stop it when the viewer exits.

## Entry points and state

- `src/cli/main.py` provides interactive chat, source Web mode, target
  add/list/remove commands, model connection commands, and local log viewing.
- `src/backend/app.py` builds the FastAPI application and registers health,
  session, query, RAG, model, and generic document routes.
- `ui/` is the TanStack Start/React client and SSR application.
- `desktop/` is an Electron wrapper for the installed Docker Web application;
  it does not start an Orion backend.
- `src/backend/sqlite_store.py` stores CLI and source-Web sessions in
  `~/.orion/sessions.db`.
- `src/backend/db.py` provides the PostgreSQL session store used when
  `ORION_DATABASE_URL` is configured; Docker Compose configures it.
- Each Web chat session owns its conversation store, Agent, evidence cache,
  investigation context, and execution lock.

Targets are stored in the JSON target registry. `localhost` always means the
environment running Orion: the local process in source mode and the
`orion-api` container in Compose. A physical host is investigated through an
explicit registered SSH target.

## Chat request flow

Normal CLI/Web agents are built by `RuntimeFactory` with a session-local
`SemanticPlannerAdapter`. The planner interprets natural-language semantics;
its output is advisory until deterministic validation succeeds.

```text
User request
  -> narrow deterministic safety/session controls
  -> bounded planner prompt
       request + relevant session context only
       no tool schema, command, credential, or evidence payload
  -> SemanticPlannerAdapter -> typed SemanticPlan
  -> SemanticPlanHarnessValidator
       -> invalid/unsafe/unconfigured: bounded clarification/refusal/setup result
       -> direct stable answer: no collectors
       -> deterministic compute: reviewed calculator
       -> capability-assisted: SemanticPlanBinder
            -> environment: ExecutionEngine
            -> current/external: ExternalVerificationExecutor
       -> multi-intent: 2-4 validated non-recursive child subplans
  -> deterministic final postconditions
       -> model relevance check when applicable
       -> at most one bounded model repair, then re-verify once
  -> response budget + universal output sanitizer
  -> response + steps + credential-safe ExecutionTrace
```

The harness owns read-only safety, target/source/freshness validation,
capability binding, execution budgets, evidence/provenance requirements, and
final hard postconditions. `KnowledgeTool` remains the only infrastructure
runtime entry point to Child Tools. Planner or model failure never grants tool
authority and never falls back to regex-first primary routing.

The first planner call receives no capability registry. Compact
`CapabilitySummaryIndex` records and `LazyCapabilityDetailExpander` implement a
post-selection disclosure contract: summaries contain no commands or parameter
schemas, and detail expansion can resolve only one already-selected capability
after a valid plan. The current `SemanticPlanBinder` then maps the validated
plan onto the existing evidence/capability/parameter pipeline; it does not send
expanded capability details back to the model.

## Tool boundary

```text
ExecutionRuntime
  -> KnowledgeTool
       -> read-only / parameter / target inspectors
       -> LinuxTool
       -> GrafanaTool
       -> ZabbixTool
       -> InternetTool
```

Child Tools own capability metadata and collection strategies. Execution
results retain typed status, failure details, Facts, provenance, and bounded
raw evidence. Only fresh `VALID` and `VALID_EMPTY` evidence satisfies a required
evidence contract.

Grafana and Zabbix registry metadata lives in tracked `tools.json`; endpoints
and tokens live outside the checkout in `/etc/orion/tool-credentials.json` for
the packaged installation. SSH host-key checking is enabled by default.

## Model boundary

- `SemanticPlannerAdapter` is the provider-neutral, schema-constrained semantic
  planning boundary. It exposes no execution or tool interface.
- `AssessmentModelAdapter`/`LLMAssessmentAdapter` provide direct-response and
  evidence-assessment model calls after routing/collection decisions are
  bounded by the harness.
- `SemanticRelevanceVerifier` can perform one compact relevance check on a
  model-generated response after hard postconditions pass.
- `SemanticResponseRepairer` can make at most one bounded repair attempt; the
  repaired candidate is verified once more with repair disabled.
- `ModelUsageRecorder` records bounded provider/model/purpose/latency and token
  metadata without prompts, credentials, or hidden reasoning text.
- `UnconfiguredAssessmentAdapter` plus `UnconfiguredPlannerProvider` keep the
  application operational in setup mode when no model connection exists.
- `MockAssessmentAdapter` and scripted planner providers are used by tests.
- Model connections are persisted by `ModelConfigStore`; the installer does
  not install model runtimes or weights.

`RuntimeFactory` reuses the selected assessment provider/fallback chain to
construct the session-local planner. Web sessions keep separate Agent/context/
cache/lock state; provider client infrastructure can be reused without sharing
mutable conversation state. Chat supports configured provider adapters.
Project RAG synthesis separately accepts the active OpenAI-compatible
connection passed by the API for that request.

## RAG boundary

The Web UI calls `/api/rag/*`; the API proxies to the internal service in
`src/tool/RAGTool/`. Every RAG project has independent documents, vector data,
BM25 data, and bounded analysis history under `RAG_DATA_DIR`. RAG is not
registered as a chat capability.

## Network and authentication boundary

Source Web mode binds FastAPI to `127.0.0.1:61888` and Vite to the configured
local frontend port. Docker Compose binds Nginx and the direct API port to
loopback; PostgreSQL, SSR UI, and RAG stay on the Compose network. The packaged
stack requires `ORION_API_KEY`; source mode leaves it optional. `/api/health`
is the only endpoint exempt from the middleware when a key is configured.
