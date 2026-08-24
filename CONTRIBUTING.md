# Contributing

Orion is being shaped around a small set of product invariants rather than compatibility with an older agent protocol.

Before changing architecture, read:

- `docs/PRODUCT.md`
- `docs/architecture/OVERVIEW.md`
- `docs/architecture/MODEL_TOOL_LOOP.md`
- `docs/architecture/TOOL_SYSTEM.md`
- `docs/architecture/RAG_AND_PROJECT_KNOWLEDGE.md`
- `docs/development/ENGINEERING_RULES.md`

## Engineering expectations

Changes should:

- preserve one Chat/Project runtime;
- keep tool choice model-driven;
- avoid semantic routing heuristics before the model;
- register tools through one registry;
- return structured tool results to the model loop;
- keep project data isolated by project scope;
- keep provider details behind model adapters;
- prefer local dependencies and local persistence;
- include focused tests for behavior changed.

## Quality checks

Current repository commands:

```bash
make test
make lint
```

Frontend:

```bash
cd ui
npm test
```

Docker:

```bash
docker compose build
docker compose up -d
docker compose ps
```

Do not change repository history or publish changes unless explicitly requested.
