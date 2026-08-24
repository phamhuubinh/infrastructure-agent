# Orion documentation

These documents define a new target architecture. They were written as a clean-sheet specification and should not be interpreted as a description of the previous implementation.

## Documentation map

### Product

- `PRODUCT.md` — users, use cases, behavior, non-goals.

### Architecture

- `architecture/OVERVIEW.md` — system decomposition and invariants.
- `architecture/MODEL_TOOL_PROTOCOL.md` — model-native tool loop.
- `architecture/DISCOVERY_TOOL_EXPOSURE.md` — dynamic tool loading/exposure.
- `architecture/CAPABILITIES.md` — canonical capability definition and registry.
- `architecture/AUTHORITY_PERMISSIONS.md` — authorization, permission, approval, budget.
- `architecture/EXECUTION_BOUNDARIES.md` — sandboxing, network, credentials, least privilege.
- `architecture/EVIDENCE.md` — evidence store, references, final grounding.
- `architecture/MODELS.md` — provider-neutral model adapters.
- `architecture/SESSIONS_CONTEXT.md` — sessions, context and bounded history.
- `architecture/PROJECTS_RAG_MEMORY.md` — project knowledge and retrieval.
- `architecture/API_BACKEND.md` — backend/service contracts.
- `architecture/EVENTS_OBSERVABILITY.md` — typed lifecycle events and metrics.
- `architecture/UI_UX.md` — operator experience.
- `architecture/FAILURE_RECOVERY.md` — bounded failures, retries and recovery.
- `architecture/SECURITY.md` — threat model and security invariants.

### Decisions

`decisions/` contains accepted ADRs for the new system only. Old historical ADRs are intentionally not part of this reset package.

### Development

- `development/CODE_AUDIT_BRIEF.md` — instructions for a deep code audit before implementation.
- `development/REBUILD_PLAN.md` — phased rebuild plan.
- `development/TARGET_CODE_LAYOUT.md` — proposed module boundaries.
- `development/ENGINEERING_RULES.md` — implementation rules.
- `development/TESTING.md` — test pyramid and gates.
- `development/MIGRATION.md` — coexistence and cutover strategy.
- `development/CLEANUP.md` — deletion rules.
- `development/ACCEPTANCE_CRITERIA.md` — definition of done.

### API

- `api/README.md` — API design principles. OpenAPI is generated from implementation and is intentionally not shipped as a hand-authored target artifact.

### Reference

- `reference/EXTERNAL_INFLUENCES.md` — architectural patterns taken from current Codex/OpenAI Agents and Claude Code documentation, with explicit differences for infrastructure use.

## Conflict rule

Accepted ADRs override architecture docs; architecture docs override development guidance. Current code never silently overrides target design.
