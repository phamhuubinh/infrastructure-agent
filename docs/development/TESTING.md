# Testing

## Testing pyramid

### Unit

Test:

- context assembly;
- deterministic model-input byte proxies for initial, resumed, and long-history turns;
- bounded model-visible ToolResult projection while canonical persistence stays complete;
- aggregate current-turn budgeting across many tool calls;
- complete historical user-turn boundaries, including an oversized tool turn;
- tool-call/result pairing, duplicate-ID rejection, collection counts, and exact
  `SourceRef` preservation under projection;
- registry/provider schema cache mutation isolation;
- tool registry;
- tool schema conversion;
- provider adapters;
- ToolResult normalization;
- project source scoping;
- document parsers/chunking/retrieval components;
- persistence.

### Contract

Verify each registered tool can be serialized to every supported provider adapter and dispatched back to the correct handler.

### Runtime vertical slices

Use fake model + fake tools:

```text
direct chat → final
chat → one tool → final
chat → several tools → final
project → project RAG → final
project → RAG + calculator → final
tool failure → model explains/uses fallback
```

### RAG

Test:

- session-source isolation;
- project-source isolation;
- exact document read;
- semantic search;
- cross-document comparison fixtures;
- deletion/reindex recovery;
- citation metadata.

### Live model

Run narrow live probes only after deterministic runtime tests pass.

Live tests should prove the configured model can naturally use model-facing tool schemas without special keyword routing.

## Current commands

```bash
make test
make lint
```

Backend:

```bash
make test-backend
```

Frontend:

```bash
make test-frontend
```
