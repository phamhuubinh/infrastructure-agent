# Orion

Orion is a security-oriented infrastructure agent runtime. It lets a language model reason about an operator request and propose calls to reviewed infrastructure capabilities without granting execution authority to natural language or to the model itself.

This repository is undergoing a **greenfield rebuild inside the existing repository**. The target design is defined by `docs/`. Existing implementation code is evidence to audit and selectively reuse; it is not an architectural constraint and does not receive compatibility priority by default.

## Product thesis

Orion combines three ideas:

1. **Model-native tool use** — the model works through ordinary tool calls and tool results rather than learning an internal harness state machine.
2. **Harness-owned authority** — the harness validates exact capability identity, schema, target/source scope, permission, approval, budget, and execution policy before any side effect.
3. **Evidence-backed answers** — executors produce structured evidence owned by the harness; the model references evidence rather than reconstructing or authorizing it.

A short formulation:

> Model proposes tool use. The harness decides whether it may execute. Executors act inside bounded environments. Evidence supports the final answer.

## Start here

Read in this order:

1. `docs/PRODUCT.md`
2. `docs/architecture/OVERVIEW.md`
3. `docs/architecture/MODEL_TOOL_PROTOCOL.md`
4. `docs/architecture/CAPABILITIES.md`
5. `docs/architecture/AUTHORITY_PERMISSIONS.md`
6. `docs/architecture/EXECUTION_BOUNDARIES.md`
7. `docs/architecture/EVIDENCE.md`
8. `docs/development/REBUILD_PLAN.md`
9. `docs/development/CODE_AUDIT_BRIEF.md`
10. `docs/development/ENGINEERING_RULES.md`

## Non-goals

Orion is not a generic autonomous shell agent, not an intent-router framework, not a multi-agent society, and not a compatibility preservation exercise for the previous runtime. It should not expose raw root shell, arbitrary HTTP, arbitrary database access, or unrestricted credentials to the model.

## Current implementation status

The documentation defines the target system. Until the rebuild is complete, code may disagree with these documents. When that happens, the disagreement is an implementation gap, not permission to weaken the target design.
