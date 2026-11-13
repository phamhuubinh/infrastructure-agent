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

Use Python from `.python-version` and Node from `.node-version` for CI parity.
The same entry point runs from PowerShell and Linux shells.

```text
python scripts/refactor/dev.py doctor
python scripts/refactor/dev.py bootstrap
python scripts/refactor/dev.py check
python scripts/refactor/dev.py build
```

Bootstrap installs the hash-verified Python development lock in `.venv` and
installs the UI through `npm ci`. Use `--backend-only` to omit UI steps.
Linux runs the full backend suite and, with the UI enabled, the installer
lifecycle check. Windows runs the native regression suite plus the shared
static and UI checks. The Linux suite owns the POSIX installer tests.

`build` writes backend and worker wheels to `release-work/dist` and the UI
bundle to `ui/dist/client`. `package` builds the checked release archives and
checksums from a clean checkout. It runs locally and does not publish them.

The lock generator uses `uv 0.13.6`. After changing dependencies, run
`python scripts/refactor/dev.py lock`, review the platform markers and
distribution hashes, and rerun bootstrap and checks.

Docker:

```bash
docker compose build
docker compose up -d
docker compose ps
```

Do not change repository history or publish changes unless explicitly requested.
