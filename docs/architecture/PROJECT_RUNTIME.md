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
- references to project documents/knowledge source.

The model still receives the same registered tool set as ordinary Chat.

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

Retrieval from Project A must not silently return Project B content.

## Model flow

```text
User asks within Project A
        ↓
Model sees:
- conversation
- active project metadata
- all registered tools
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

A Project question may legitimately require several tools:

```text
project requirement
+ Internet vendor documentation
+ calculator sizing
+ Grafana actual metrics
→ recommendation
```

The runtime must allow the model to combine them naturally in one conversation loop.
