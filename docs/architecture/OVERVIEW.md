# Architecture overview

## Design target

Orion is a local-first conversational runtime with automatic model-driven tool use.

The architecture is intentionally centered on one loop:

```text
┌───────────────┐
│     USER      │
└───────┬───────┘
        │ message
        v
┌────────────────────────────┐
│ ORION CONTEXT ASSEMBLY     │
│                            │
│ session/history            │
│ current attachments        │
│ active project (optional)  │
│ project metadata           │
└──────────────┬─────────────┘
               │
               v
┌────────────────────────────┐
│           MODEL            │
│ all registered schemas     │
│ from the first turn         │
└──────────┬───────────┬─────┘
           │           │
     final answer      │ tool call
           │           v
           │   ┌───────────────────┐
           │   │ ORION TOOL HUB    │
           │   │ validate contract │
           │   │ dispatch tool     │
           │   └─────────┬─────────┘
           │             │
           │             v
           │      ┌───────────────┐
           │      │ TOOL / SOURCE │
           │      └───────┬───────┘
           │              │ result
           │              v
           │      ┌───────────────┐
           │      │  TOOL RESULT  │
           │      └───────┬───────┘
           │              │
           │              └─────────────> MODEL
           v
┌────────────────────────────┐
│       FINAL RESPONSE       │
└────────────────────────────┘
```

## Responsibility split

### Model

The model owns semantic reasoning:

- understand the user's request;
- decide whether existing context is sufficient;
- choose a registered tool when useful;
- combine multiple tool/source results;
- ask a clarification if necessary;
- produce the final answer.

### Orion

Orion owns deterministic application behavior:

- persist sessions/projects/documents;
- assemble known context;
- register and describe tools;
- validate model tool-call structure;
- invoke the selected tool;
- return structured results to the model;
- stream/persist public runtime events;
- keep project/session data scoped correctly;
- manage model provider adapters.

Orion does **not** own a separate semantic intent classifier before the model.

## Local-first

Primary dependencies should be runnable locally:

- backend;
- UI;
- persistence;
- RAG/index;
- vector database;
- model endpoint when the user provides one locally.

Remote models or Internet integrations are optional integrations, not architectural assumptions.

## Chat and Project

There is one runtime.

```text
Chat = base runtime
Project = base runtime + project-scoped knowledge
```

Do not fork the agent/tool implementation for Project.

## Remote Endpoint v1

See [endpoint runtime and threat model](ENDPOINTS.md) and
[ADR 0015](../decisions/0015-paired-endpoint-execution.md) for the additive worker
transport, identity persistence, fixed tool family and independent policy ceiling.

Remote Endpoint v1's primary mode is a zero-install **Remote Control** portable
worker with temporary in-memory credentials, foreground Disconnect/Exit and
explicit remembered mode. Its endpoint workspace contains Device Chat, Desktop,
Files, Processes, Browser and Connection. Device Chat uses the same canonical
ChatRuntime with persisted server-owned endpoint binding, separate history/mutation
mode and no Project/attachments. Cross-device endpoint calls are rejected.
Portable platform artifacts carry version/source SHA/checksums; source builds
without compatible release metadata show unavailable. Confirmed End & forget
removes endpoint-owned metadata/history under existing active-request safeguards.
See the endpoint operations/architecture reference for platform prerequisites,
cleanup/expiry, download integrity and native artifact smoke coverage.
