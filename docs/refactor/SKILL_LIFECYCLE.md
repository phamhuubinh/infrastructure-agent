# R10 product skill implementation boundary

This records the implemented package/service/runtime/operator boundary. R10 still
requires current full regression and the workflow/policy checks recorded below;
package files alone are not acceptance evidence.

## Package and trust

Support bundled, explicitly installed user and bound Project packages. Never scan
development/global Codex skills or arbitrary parent directories. The development
orion-refactor/Graphify skills are not product packages. Skill content cannot grant
tool permissions, change a scope, execute a script or create a new model/agent.

Validate bounded SKILL.md frontmatter, product audience, semantic version, name,
description, scopes and required capabilities. Reject duplicate/unknown metadata,
YAML aliases/tags, missing capabilities and unsafe resource paths. Enumerate only
the selected package, refusing links, hardlink aliases, hidden/private paths,
special files, directory escape, excessive resources/bytes and invalid text.
No Markdown link automatically authorizes a file read outside the package.
Scripts are resources to read; execution always uses canonical command tools and
their current mutation mode, exact target confirmation and OS ceiling.

## Storage and lifecycle

Store owner-installed immutable package manifests and bounded resource bytes in
SQLite, keyed by a content digest, with separate owner/scope/enabled catalog rows.
This keeps install/update/disable/remove transactional and includes installed
skills in the existing managed SQLite export/import, without adding an unexported
filesystem store. Bundled packages are wheel resources; source development uses
only the explicit repository skills/builtin location. No second hand-maintained
copy of bundled guidance is introduced.

Operator installation/update reads one explicit local package path and preserves
version/hash identity. Neither a model tool nor a retrieved webpage installs a
package. The CLI owns package mutation; product model tools only list/load/read
already trusted scoped packages. Disable/remove blocks new request selections.
Each active request pins its catalog/version snapshot and already selected guidance;
an owner can Stop that request before starting one with changed skill policy.
Old immutable bytes remain only while a catalog or active request snapshot refers
to them; garbage collection operates on owned SQLite package rows, not user files.

## Runtime and resources

Keep one ChatRuntime. Expose bounded applicable catalog descriptions and canonical
skill list/load/read schemas on the first supported model turn. Explicit first-line
`/skill <name>` invocation selects existing guidance; ordinary semantic/model tool
selection uses the catalog, with no separate keyword/AI planner or pre-router.

Skill guidance is lower than application scope and user instructions. Integrate
selected guidance through the existing bounded context path, separate from source
evidence/citations. Preserve the same pinned guidance over compaction/continuation.
Resource reads require the current Orion request and actual principal/workspace/
session/Project/endpoint identity; names/digests are not authorization. Project
packages cannot appear in ordinary Chat, another Project or Device Chat. Scope
metadata can further limit bundled/user skills to chat/project/device surfaces.

With skills enabled, the runtime uses a 32,768-byte local context ceiling so its
bounded catalog/guidance does not consume the entire previous 12,000-byte envelope
and evict the tool continuation. A configured smaller profile limit still wins;
the existing complete-block compaction and explicit omission notices still apply.
Guidance itself is limited to four packages and 8,192 UTF-8 bytes per request.

The offline operator CLI is `orion skill list|install|update|enable|disable|remove`.
Installation takes an explicit directory; update also checks the installed name.
Use `--source project --project ID` to bind a package. Stop the runtime first:
the same exclusive database lease protects these operations. Updates preserve
the enabled preference; bundled packages can be disabled but cannot be removed.

Use bounded transient request results for skill resources; do not turn a skill
script or instruction payload into persistent assistant/tool history that applies
to unrelated future requests. End/Stop/failure clears request-owned skill state.
Missing tools/resources, disabled/unavailable/version-changed skills return explicit
errors. No fallback broadens scope or pretends a successful load/execution.

## Required verification

Test package validation/traversal/link/size/hash, versioned atomic lifecycle,
owner/workspace/Project/device isolation, current-request catalog pin and cleanup,
first-turn schema/catalog availability, explicit and model selection, bounded
context/compaction, unavailable capability/resources and scripts through ordinary
authorization. Exercise windows-linux-ops, project-research and mcp-workflows in
the real runtime with fixture providers/tools. Keep native/live gates separate.
