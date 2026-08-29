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

The model receives structural discovery for registered tool names and autonomously decides:

- whether a tool is needed;
- which tool is appropriate;
- what arguments to provide;
- whether another tool call is useful after receiving a result;
- when enough information exists to answer.

When a tool is useful, the model first requests one or more exact registered names
through the generic expansion control, then calls from that request-local subset.

Orion itself does not infer semantic intent before the model with keyword rules, regex lists, bilingual aliases, or a separate tool-selection classifier.

## RAG behavior

RAG is not always-on prompt augmentation.

The model can use document retrieval when it needs document evidence.

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
