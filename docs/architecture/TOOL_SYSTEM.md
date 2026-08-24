# Tool system

## Goal

Tools give the model capabilities beyond its static parameters while keeping orchestration simple.

## One registry

There should be one authoritative registry containing every tool available to the runtime.

Conceptually:

```python
ToolDefinition(
    name="internet.search",
    description="Search the Internet",
    input_schema={...},
    handler=...
)
```

The exact implementation may differ, but tool identity, schema, description, and handler binding should not be duplicated across multiple selectors/routers.

## Startup

```text
application startup
       ↓
discover/register configured tools
       ↓
validate tool definitions
       ↓
build model-facing tool schemas
       ↓
all registered tools available to every Chat/Project model turn
```

## Runtime

```text
Model ToolCall
   ↓
tool exists?
   ↓
input schema valid?
   ↓
ToolRunner
   ↓
tool implementation/integration
   ↓
structured ToolResult
   ↓
Model
```

Orion validates structure and dispatches. It does not second-guess the semantic reason the model chose the tool.

## Current families

The current repository contains:

- Knowledge/RAG;
- calculator;
- Internet;
- Linux;
- Grafana;
- Zabbix.

These should be integrated into the same model-facing registry rather than separate semantic pipelines.

## Configuration

Global application settings may determine whether an integration is actually configured/available. This is different from a conversation tool picker.

A tool that cannot initialize because required integration configuration is missing should be reported unavailable at startup/health time rather than represented as a manually disabled chat choice.

## Tool output

Tool results should be:

- structured where practical;
- bounded enough for the model/context;
- explicit about errors;
- tagged with useful source metadata;
- free of raw credentials/secrets.

Large payloads should be summarized/indexed or referenced rather than blindly injected.
