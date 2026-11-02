# Skills

> Full implementation requirements now live in [DESIGN.md](../refactor/DESIGN.md)
> and [R10](../refactor/WORK_PLAN.md). The package/service/runtime/CLI contract is
> implemented in [SKILL_LIFECYCLE.md](../refactor/SKILL_LIFECYCLE.md). Development
> orion-refactor/Graphify skills are excluded from the product catalog.

## Status

Product packages, owner/Project catalogs, immutable SQLite resources, transactional
lifecycle and runtime list/load/read are implemented. Operator installation uses
the offline `orion skill` CLI. Bundled packages ship as wheel resources. A dedicated
skill management UI is still part of the shared client work, not an existing UI.
See [source evidence](../refactor/evidence/R10_SESSION_2026-10-31.md) for test scope.

## Role

A skill is a reusable instruction set describing how to perform a class of tasks
with tools. It is not a model, AI agent, worker or execution permission.

The model can apply skill guidance while continuing the ordinary ChatRuntime loop.
Every actual operation still resolves through the canonical registry and ToolRunner.
A skill can guide use of the explicit [Windows/Linux command tools](SYSTEM_COMMANDS.md)
when authorized; it cannot create hidden execution paths/tools, switch
principal/project/endpoint identity or widen a server/worker policy.

## Instruction and resource contract

Each package has an identity/version/hash, description, product audience, scopes,
capabilities, instructions and optional bounded resources. The loader does:

- load only explicitly configured trusted skill packages or user-invoked guidance;
- include applicable guidance within the ordinary bounded context path;
- keep resource reads inside the permitted package and runtime scope;
- distinguish task instructions from untrusted pages, documents and tool output;
- identify missing tools/resources instead of inventing successful execution;
- preserve user instructions, application scope and permission checks.

No independent planner, model invocation or agent lifecycle selects a skill.
The first model turn receives an applicable catalog and canonical schemas.
First-line `/skill name` explicitly selects guidance; skill.load can select the
same pinned package from the current request. Update/disable/remove affects new
requests; active request snapshots retain their exact version until Stop/end.
Installed package resources participate in managed-data export/import.

## Scopes

Project-specific guidance may apply only in that Project. Device Chat cannot load
Project guidance indirectly through a skill. A selected skill must be applicable
to the current legitimate conversation scope; resources from another conversation,
Project or device are not available merely because the skill names them.

## Acceptance

Verify same-runtime execution, bounded guidance loading, unavailable-resource
errors, instruction trust boundaries and inability to escape Project/device scope
or mutation permissions. Skill installation/update tooling remains separate from
executing the user task.
