# ADR 0018 — Clean-slate refactor and cross-platform product

## Status

Current target decision, 2026-10-29. The user requests a complete implementation
brief: documentation first, then whole-repository refactor with authority to
replace/delete irrelevant source, tests, docs, configuration and build files.
A subsequent steering message narrows AI providers to DeepSeek, Claude and OpenAI.

## Decision

[REFACTOR_REQUEST.md](../../REFACTOR_REQUEST.md) and
[docs/refactor/DESIGN.md](../refactor/DESIGN.md) are the authoritative specification.
They supersede conflicting older architecture/product/development instructions.

Deliver one model/runtime with provider adapters, command tools, real skill
loading/bundled workflows and MCP host capabilities; Windows desktop app, Linux
headless CLI/service, web, Android and iOS clients share contracts and behavior.
Use [PROVIDERS.md](../refactor/PROVIDERS.md) for the three-vendor API boundary.

The architecture is a clean sheet, not an obligation to preserve the old stack,
layouts, tests or operation wrappers. Defaults are chosen to make execution
concrete, with evidence-based ADR changes permitted. Retain correct code by
decision, not inertia. Remove obsolete monitoring/vendor paths and inspect every
file/caller before deletion; preserve real data/credentials and Git history.

## Autonomous implementation contract

The user has authorized routine structural changes, rewrites, dependency changes
and deletion of obsolete repository files without repeated confirmation.
Follow [AUTOMATION.md](../refactor/AUTOMATION.md), task graph and evidence gates.
External credentials/runners/signing limitations remain explicit needs_external,
while independent work continues. This authority does not remove product
authorization or authorize store publication/paid operations without bounds.

## Evidence boundary

This phase writes the implementation request, task list, skill packages and
read-only inventory/task tools. It does not claim the new provider adapters,
command runner, native apps or product skill loader are implemented.
Whole-file inventory/hashes are not whole-code semantic review; R01/R19 and
platform/provider gates remain pending in STATE.json.
