# Testing

## Testing pyramid

### Unit

Test:

- context assembly;
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
