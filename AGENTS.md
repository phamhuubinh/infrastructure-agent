# Repository instructions for coding agents

## Mission

Treat this repository as a **greenfield rebuild of Orion inside an existing codebase**. Do not perform a compatibility-driven refactor of the old runtime. Audit existing code for reusable implementation components, then build toward the target contracts in `docs/`.

## Authority order

1. `docs/decisions/` — accepted architectural decisions.
2. `docs/architecture/` — target system contracts.
3. `docs/development/` — implementation and validation rules.
4. `docs/PRODUCT.md` — product behavior.
5. Current source/tests — implementation evidence only.

If old code conflicts with the target architecture, prefer rewriting or deleting the old code unless a documented compatibility requirement says otherwise.

## Mandatory design rules

- The model uses a model-native tool loop: tool calls and tool results.
- Do not recreate `ACTION_DETAIL`, `OBSERVATION`, `FEEDBACK`, selection-as-action, or another model-visible harness state machine.
- A model tool call is a proposal, never execution authority.
- Natural-language text is never capability, target, source, permission, approval, credential, or shell authority.
- Tool exposure is explicit runtime state. A registered-but-unexposed capability is not callable.
- One canonical `CapabilityDefinition` must be the source of truth for model schema, authority validation, executor binding, result contract, and evidence projection.
- Capability/target/source identities resolve exactly. No aliases, fuzzy matching, semantic fallback, or implicit localhost.
- Permission, approval, and execution isolation are separate layers.
- The model never receives raw credentials, internal secret configuration, private keys, bearer tokens, or unrestricted low-level execution primitives.
- Harness-owned evidence is immutable after creation. The model references evidence IDs instead of recreating evidence fields.
- Repeated identical successful calls must not repeat side effects; reuse existing evidence or fail boundedly.
- No semantic pre-router decides intent/tool/target/source from user prose before the model.
- One authoritative agent is the default. Do not introduce multi-agent routing unless a future ADR explicitly requires it.

## Work sequence

For a large rebuild task:

1. Read target docs.
2. Audit callers/imports/config/persistence for the affected subsystem.
3. Produce a KEEP / ADAPT / REWRITE / DELETE disposition.
4. Define new contracts and tests before wiring production execution.
5. Implement vertical slices through model → harness → authority → executor → evidence → final.
6. Remove superseded code rather than preserving parallel runtimes.
7. Run focused tests and static checks.
8. Run live-model/Docker/release gates only when explicitly requested.

## Git

Do not commit, push, reset, rebase, stash, clean, or create branches unless explicitly requested by the user.
