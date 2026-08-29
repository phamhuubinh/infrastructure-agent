# Rebuild guide

**Status: implementation guidance only. Reading this file does not initiate a rebuild.**

Use this only when the user's current task explicitly requests implementation work.

## Suggested sequence

### 1. Freeze core contracts

Define:

- internal chat/timeline messages;
- ModelBackend;
- ToolDefinition/ToolCall/ToolResult;
- ToolRegistry/ToolRunner;
- Session/Project entities;
- KnowledgeSource/document contracts.

### 2. Build one minimal Chat vertical slice

```text
message
→ context
→ model
→ final
```

### 3. Add tool loop

```text
model
→ registered tool
→ ToolResult
→ model
```

Use calculator/fake tool first.

### 4. Integrate RAG as a tool/source

Add:

- session attachment source;
- project source;
- exact scoped retrieval;
- citation metadata.

### 5. Reuse/migrate current tool families

Adapt existing:

- Internet;
- Linux;
- Grafana;
- Zabbix;
- Knowledge/RAG;
- calculator.

Each joins the same ToolRegistry/ToolRunner.

### 6. Cut Project onto Chat runtime

Delete any duplicate Project agent/router. Project should supply context/source scope only.

### 7. Cut API/UI

Remove tool selection UX and any request fields whose only purpose is user tool choice.

### 8. Delete obsolete architecture

After reachability proves the new runtime owns all user requests, remove superseded:

- semantic tool selector;
- old agent decision FSM;
- legacy dynamic exposure/discovery stages not derived from the canonical registry;
- duplicated authority/evidence abstractions not needed by the current product;
- stale tests/fixtures for the old protocol.

## Important

Do not preserve old abstractions merely because migration seems easier. Also do not perform any step above unless explicitly tasked to modify code.
