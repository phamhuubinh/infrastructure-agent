# Adding a tool

## Goal

A new tool should become automatically usable by the model without adding a semantic router rule or UI selector.

## Required pieces

A tool needs:

1. unique stable model-facing name;
2. concise description explaining when it is useful;
3. exact input schema;
4. handler/executor;
5. structured result/error contract;
6. registration;
7. tests;
8. configuration/health handling if it depends on an integration.

## Registration invariant

After successful application registration:

```text
new tool
  ↓
tool registry
  ↓
model-facing schema on Chat and Project turns
```

Do not separately edit:

- keyword intent maps;
- Vietnamese/English alias tables;
- per-screen tool lists;
- model workflow FSMs.

## Description quality

Tool descriptions are part of model usability. Explain what the tool does and important argument semantics, but do not encode a huge decision tree in the system prompt.

## Tests

Test:

- registration;
- schema validation;
- success;
- failure;
- model adapter serialization;
- ToolResult continuation.
