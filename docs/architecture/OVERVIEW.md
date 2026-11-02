# Architecture overview

## System boundary

Orion has one main conversational runtime, one canonical tool registry and one
execution/authorization path. Chat, Project and Device Chat are scoped entry
points into that runtime. There are no per-project, per-tool or per-device AI
agents. A worker executes operations; a job schedules runtime requests.

```text
Browser: Chat | Projects | Remote Control
                      │ HTTPS + owner session in remote mode
                      ▼
              API / scope binding / streaming
                      │
                      ▼
                 ChatRuntime ─────────── ModelBackend
                      │                  configured inference endpoint
                      ├── ContextBuilder
                      │    ├── canonical conversation projection
                      │    └── project/attachment or bound device metadata
                      │
                      └── ToolRunner + frozen ToolRegistry
                           ├── KnowledgeService → documents / retrieval
                           ├── calculator / Internet
                           ├── Windows/Linux command runner (target)
                           ├── MCP proxies
                           ├── scheduler management → same ChatRuntime
                           └── EndpointManager
                                      ▲
                                      │ worker-initiated outbound WSS
                                portable worker
                                  └── local system/files/process/browser/desktop
```

The [consolidated baseline](BASELINE_2026-10-29.md) defines the current product
boundary, amended by [ADR 0017](../decisions/0017-windows-linux-command-focus.md).
Dedicated monitoring adapters are retired from the target. The
[command family](SYSTEM_COMMANDS.md) is the primary Windows/Linux path and remains
unimplemented. [Contracts](CONTRACTS.md) define data identities; the
[implementation inventory](../development/IMPLEMENTATION_STATUS.md) records source
evidence without claiming test success.

## Responsibility split

| Component | Responsibility |
| --- | --- |
| Web UI/API | Resource selection, authentication, scope binding, streams and direct user actions |
| ChatRuntime | Same model → tool → result → model loop for every conversation surface |
| ContextBuilder | Bounded projection of current request, legitimate history and explicit scope |
| ModelBackend | Provider-neutral request/response mapping; one configured reasoning path per request |
| ToolRegistry/ToolRunner | Tool definitions, closed-schema checks, scope, permissions, dispatch and results |
| KnowledgeService | Document ingestion, scoped retrieval, exact reads and provenance |
| EndpointManager | Pairing, device identity/channel, operation lifecycle and manual control sessions |
| Portable worker | OS operation executor with independent local policy; no model/prompt authority |
| Command executor (target) | PowerShell/cmd/sh/bash over worker or configured SSH; bounded process/output lifecycle |
| Scheduler | Persisted schedule/claim lifecycle and read-only requests into the same runtime |
| Skill instructions (target) | Reusable trusted task guidance over tools; no new runtime or permissions |

The model decides semantically whether a tool is useful. Orion must not add a
semantic pre-router or duplicate a tool schema in a selection service. All
registered model-callable schemas are visible from the first model turn (ADR
0007); this is independent of execution authorization.

## Request flow

1. Authenticate the caller and resolve the session, Project or device from
   application-owned state.
2. Build bounded context with the complete current user request, legitimate
   conversation history, explicit scope metadata and registered schemas.
3. Ask the configured model for an answer or tool calls.
4. Validate each tool call, attach RuntimeScope and enforce the session mutation
   mode plus any server/worker ceiling.
5. Dispatch eligible operations, correlate structured ToolResults and return them
   to the same model.
6. Validate terminal provenance/format contracts, stream and persist public state.

Independent safe reads may execute together. Mutations are ordered and never
automatically replayed after an ambiguous side effect. A confirmation pauses
the existing request; it does not invoke another AI agent.

## Data boundaries

- Chat has its own history and attachments.
- Project adds project instructions/documents to its conversations.
- Device Chat has endpoint-owned history, no Project or attachment scope, and a
  server-owned endpoint_id enforced on every endpoint call.
- Configured infrastructure target references do not replace application scope.
- Secrets stay in the server/worker credential path, outside prompts and results.
- Retrieved content and worker observations are untrusted evidence.

See [Context](CONTEXT_AND_MEMORY.md), [Project](PROJECT_RUNTIME.md),
[Endpoints](ENDPOINTS.md) and [Security](SECURITY_LOCAL_FIRST.md).

## Local-first implementation baseline

Reuse the current Python backend, provider adapters, SQLite persistence, local
blob/document storage and TypeScript UI. Local learned embeddings and hybrid
retrieval are configured capabilities. A separate vector service, broker, cloud
control plane or new framework is not required by the redesign.

The default server binds loopback. Remote browser access is an explicit owner
authentication boundary behind HTTPS. Workers connect outward to a reachable
Orion server; opening its website does not expose the browser host's OS.
Model inference may be local or remote through the existing provider adapter.

## Extension and lifecycle

MCP proxies join the registry before freeze. Connecting/disconnecting devices does
not add model tools dynamically; a stable endpoint family resolves live devices.
Skills, when implemented, join context as trusted bounded task instructions and
must not bypass the registry. Background work calls the same runtime with explicit
scope. [Reconciliation](../development/REBUILD_GUIDE.md) starts with source
verification and reuse rather than a destructive rebuild.
