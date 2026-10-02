# Product

## Mission

Orion is a **local-first AI technical workbench** for technical work.

It provides one conversational surface for:

- general technical chat;
- reading and understanding documents;
- project-specific knowledge work;
- comparison and analysis;
- deterministic calculation;
- Internet research;
- Linux inspection/actions exposed by the installed tool;
- Grafana queries;
- Zabbix queries;
- persisted one-time and recurring read-only executions;
- future technical integrations.

The user's job is to state the task. The user should not need to choose whether Orion needs RAG, Internet, calculator, Linux, Grafana, or Zabbix.

## Primary surfaces

### Chat

Chat is the default workspace.

Each conversation exposes a mutation permission beside the composer model control:
`Chỉ đọc` (default), `Hỏi trước khi sửa` (confirm each exact mutation), or
`Tự động sửa` (auto allow eligible configured mutations after one warning). This is
saved per conversation and applies equally in Project. A confirmation pauses the
same request before the mutation handler; denial returns to the model. Tool choice
stays with the model and hard target/schema/server restrictions still apply.

It contains:

- conversation history;
- current user message;
- session attachments;
- model configuration;
- registry-derived structural tool discovery and model-controlled expansion.

### Project

Project is not a different agent.

Project is:

```text
Chat runtime
+ active project identity
+ project metadata/instructions
+ persistent project documents
+ project-scoped RAG source
```

All ordinary tools remain available in Project.

## Tool behavior

There is no tool picker.

The model receives all registered model-callable tool schemas on the first turn and autonomously decides:

- whether a tool is needed;
- which tool is appropriate;
- what arguments to provide;
- whether another tool call is useful after receiving a result;
- when enough information exists to answer.

When tools are useful, the model calls ordinary registered tools directly. Independent
reads with known inputs may be called together before the synthesis turn.

Orion itself does not infer semantic intent before the model with keyword rules, regex lists, bilingual aliases, or a separate tool-selection classifier.

## Internet grounding

Internet search is discovery-only in the model loop. Model-visible search rows expose bounded
selection metadata (title, URL, and retrieval time), not claim-bearing snippets or citable
`evidence_ref` values. The model fetches a chosen page to obtain citable web evidence. For exact
latest/current web claims such as a release, version, date, or status, it must ground synthesis in
authoritative fetched evidence. Citation provenance does not by itself establish semantic
entailment.

## RAG behavior

RAG is not always-on prompt augmentation for unrelated requests.

When an answer depends on document contents, the model must retrieve current document evidence
before synthesis. `knowledge.search` is the default discovery path when no exact target document
is already visible or when retrieval spans the available knowledge scope. A current-session
attachment with a visible exact `document_id` may be read directly. `knowledge.list_documents`
is metadata browsing, not a content-QA preflight.
The active Project contributes bounded ready-document names, types, and status to model context.
A request by Project filename uses `knowledge.search` for content evidence and exact document ID.
Orion documents are not infrastructure filesystem paths.

Knowledge sources can include:

- current/session attachments;
- project documents when a project is active;
- an optional global/local knowledge library if configured.

Project knowledge must remain isolated by project.

## Scheduled tasks

Chat and Project can create, inspect, pause, resume and delete scheduled tasks through
model-callable scheduler tools. One-time schedules use an aware timestamp; recurring
schedules use minute-precision cron with an explicit timezone. Task creation and
management mutations obey the conversation's permissions. Each task has its own
execution conversation and persisted history linked to ordinary Chat requests.

Scheduled execution is always read-only, even when the task conversation's saved
permission allows mutations. Project tasks retain their Project knowledge and
instructions; ordinary conversation attachments are not copied. After downtime,
one-time tasks run once and recurring tasks coalesce missed occurrences into one
catch-up run. There is no dedicated Scheduler UI in v1.

## Current scope priority

The first priority is excellent:

1. Chat;
2. Project;
3. document ingestion and understanding;
4. automatic tool use;
5. local model support;
6. reliable persistence and UI.

Infrastructure automation can grow from the same tool loop, but it must not distort the Chat/Project architecture.

## User experience principles

- Ask naturally; do not select a tool first.
- Project feels like Chat with additional private project knowledge.
- Tool activity may be visible for transparency, but is not a configuration burden in the conversation flow.
- Document-grounded answers should identify their sources.
- If a tool/source fails, Orion should explain the missing information instead of pretending it succeeded.
- Local operation is the default deployment assumption.

## Paired remote endpoints

Chat/Project can operate explicitly paired Windows/Linux devices with the same
runtime and mutation modes. The authenticated Thiết bị page adds pairing, identity
management, bounded file transfer and optional manual Remote Desktop. Capabilities
remain limited by local worker policy. See [endpoint operations](operations/ENDPOINTS.md).

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
