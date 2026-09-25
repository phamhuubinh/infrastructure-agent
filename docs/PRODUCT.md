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
- future technical integrations.

The user's job is to state the task. The user should not need to choose whether Orion needs RAG, Internet, calculator, Linux, Grafana, or Zabbix.

## Primary surfaces

### Chat

Chat is the default workspace.

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

Knowledge sources can include:

- current/session attachments;
- project documents when a project is active;
- an optional global/local knowledge library if configured.

Project knowledge must remain isolated by project.

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
