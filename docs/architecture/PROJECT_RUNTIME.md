# Project runtime

## Principle

A Project is **Chat plus persistent project knowledge**.

It is not a separate agent, separate model protocol, or separate tool selector.

## Project context

When a chat is associated with an active project, Orion deterministically includes:

- project ID;
- project name;
- safe project metadata;
- project instructions/description when configured;
- references to the project's documents/knowledge source.

The model receives the same registry-derived structural discovery enum and generic expansion control
as ordinary Chat; Project does not own a separate tool protocol.

## Scope ownership

Project identity is application state owned by Orion.

The model does not choose an arbitrary project by inventing a `project_id` in ordinary retrieval arguments.

Conceptually:

```text
Session / Project state
       ↓
active_project_id = Project A
       ↓
RuntimeScope(project_id=Project A)
       ↓
model tool call
       ↓
ToolRunner
       ↓
project-aware tool receives the bound RuntimeScope
```

This separates responsibilities cleanly:

```text
Model:
- decides whether project knowledge is needed;
- decides the search/read query;
- reasons over returned material.

Orion:
- decides which Project the conversation belongs to;
- binds exact project scope;
- prevents cross-project retrieval leakage.
```

See `CONTRACTS.md` for the canonical `RuntimeScope` contract.

## Project knowledge

Project documents form an additional RAG source:

```text
Project A
  └── project_source:A
       ├── requirements.pdf
       ├── proposal.docx
       └── sizing.xlsx-derived text/metadata

Project B
  └── project_source:B
       └── ...
```

Retrieval from Project A must never silently return Project B content.

## Model flow

```text
User asks within Project A
        ↓
Orion assembles deterministic context:
- conversation
- active Project A metadata
- current attachments
        ↓
Model sees the registry-derived structural discovery enum
        ↓
Model may:
- answer directly
- search/read project knowledge
- search the Internet
- calculate
- query Linux/Grafana/Zabbix
- combine these sources
        ↓
Final answer
```

There is no "Project tool mode" and no tool checkbox.

## Cross-source reasoning

A Project question may legitimately require several sources:

```text
project requirement
+ Internet vendor documentation
+ calculator sizing
+ Grafana actual metrics
→ recommendation
```

The runtime must allow the model to combine them naturally in one conversation loop.

## Project lifecycle

At minimum a Project should support:

```text
create
read/update metadata
document upload
document ingestion status
document delete
project conversations
project delete/archive according to product behavior
```

Deleting a project/document must also remove or tombstone its retrievable index entries so stale content cannot reappear.
