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

Explicit targets are stored in the JSON target registry. At runtime
construction, Orion also discovers concrete aliases declared by the local SSH
configuration (including unconditional `Include` files) and registers them
only for that runtime; wildcard aliases are ignored and explicit JSON targets
take precedence. `localhost` always means the environment running Orion: the local
process in source mode and the `orion-api` container in Compose. A physical
host is investigated through an explicit or discovered SSH target.

## Chat request flow

Configured CLI/Web agents are built by `RuntimeFactory` with
`AgentControllerLoopCoordinator` and `ControllerAdapter` as their primary
natural-language path. The responsibility boundary is:

> **Model owns reasoning and next-action selection. Harness owns authority,
> execution, evidence and completion.**

| Owner | Implemented responsibility |
|---|---|
| Model/controller | Interpret the bounded current request/context; return one `FINAL`, `DISCOVER`, `ACTION`, `CLARIFY`, or `REFUSE` decision; select a registered capability ID and typed arguments only after applicable disclosure; produce a final candidate. |
| Harness | Build hard constraints; enforce safety, target/source, availability, read-only and budgets; disclose capabilities; validate and execute actions; serialize evidence; update accepted session context; perform completion/final checks; sanitize, budget, trace, and deliver one response. |

```text
User request
  -> HardRequestConstraintsBuilder
       sensitive-disclosure and mutation stops can finish before a model/action/tool call
  -> bounded validated session context + fixed small capability categories
  -> ControllerAdapter -> exactly one decision
       FINAL | DISCOVER | ACTION | CLARIFY | REFUSE
  -> DISCOVER: one approved category -> bounded summaries -> controller
  -> ACTION: selected capability detail/typed schema -> controller typed arguments
             (disclosure is not execution)
  -> AgentActionValidator -> compact control feedback, or approved action
  -> AgentActionExecutor -> one validated action -> compact observation
       host/Grafana/Zabbix: KnowledgeTool / Child Tool boundary
       Internet: ExternalVerificationExecutor / InternetTool boundary
       calculator: first-class compute.deterministic action
  -> controller selects the next bounded decision
  -> deterministic completion/final boundary -> sanitizer/budget -> one response
```

`AgentActionValidator` is the deterministic authority for registered action
IDs, typed parameters, exact target/source constraints, availability,
read-only policy, and budgets. `AgentActionExecutor` dispatches only a
validated approved capability. An action is structured intent, never a shell
command: the model cannot make arbitrary shell or HTTP work execute. Generated
shell, YAML, or GitHub Actions content remains output text or an artifact and
does not grant authority.

The first controller turn receives fixed small capability categories, not the
full registry or schemas. A `DISCOVER` decision reveals only one requested
approved category as bounded summaries. When an `ACTION` needs it, the harness
discloses exactly the selected capability detail and typed schema before the
controller supplies arguments. It does not execute during this handshake, and
unknown, blocked, or invalid actions do not trigger an automatic harness
repair/retry.

The loop and controller/model/action/tool/discovery/input/completion budgets
are finite. A controller round is not a tool call. Compact observations contain
only safe status, bounded facts/provenance and control codes; they do not replay
raw commands, raw evidence, credentials, prompts, or hidden reasoning.

The older `SemanticPlannerAdapter`, `SemanticPlan`, and `SemanticPlanBinder`
remain in explicit setup-mode, compatibility, and historical code paths where
needed; they are not the configured RuntimeFactory primary path.

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

- `ControllerAdapter` is the provider-neutral, schema-constrained Agent v2
  decision boundary. It has no execution interface and can select only
  registered capability IDs and typed arguments presented through the bounded
  disclosure protocol.
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
construct the session-local controller. Web sessions keep separate
Agent/context/cache/usage/lock state; provider client infrastructure can be
reused without sharing mutable conversation state. Chat supports configured
provider adapters.
Project RAG synthesis separately accepts the active OpenAI-compatible
connection passed by the API for that request.

## RAG boundary

The Web UI calls `/api/rag/*`; the API proxies to the internal service in
`src/tool/RAGTool/`. Every RAG project has independent documents, vector data,
BM25 data, and bounded analysis history under `RAG_DATA_DIR`. RAG is not
registered as a chat capability.

Generic Chat attachments remain outside that service. `/api/query` injects
only bounded, untrusted evidence built from the active server-owned session's
attachments: small extracted text is direct context, while larger text uses
request-local deterministic retrieval. Attachment IDs, storage paths, and
project IDs are not controller authority or prompt context.

## Network and authentication boundary

Source Web mode binds FastAPI to `127.0.0.1:61888` and Vite to the configured
local frontend port. Docker Compose binds Nginx and the direct API port to
loopback; PostgreSQL, SSR UI, and RAG stay on the Compose network. The packaged
stack requires `ORION_API_KEY`; source mode leaves it optional. `/api/health`
is the only endpoint exempt from the middleware when a key is configured.
