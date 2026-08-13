# 07 - Development Rules

These rules apply to all repository work.

## 1. Repository truth

Inspect current code, configuration, schemas, and tests before changing the
system. Reuse existing abstractions and correct documentation that disagrees
with the repository. Do not create parallel implementations.

## 2. Current architecture is authoritative

Preserve the responsibilities and dependency direction documented in
`02_CURRENT_ARCHITECTURE.md`. Architecture changes require explicit approval,
motivation, trade-off analysis, and impact analysis.

## 3. Deterministic before AI

Use deterministic logic for request semantics, target/source resolution,
parameter validation, evidence/capability selection, execution, aggregation,
thresholds, and safety policy. The model explains evidence; it does not control
investigation or tools.

## 4. Responsibility boundaries

| Component | Responsibility |
|---|---|
| Assessment Model | Evidence interpretation and user-facing explanation |
| DeterministicAgent | Routing, response orchestration, and session-aware context |
| Execution Engine | Infrastructure investigation execution |
| KnowledgeTool | Capability aggregation and dispatch |
| Child Tool | Evidence collection for one domain |
| Environment | Source of operational truth |

Project RAG remains isolated from Chat and uses its own project/document
lifecycle.

## 5. Evidence first

Improve in this order: Tool -> Evidence -> Assessment. Do not compensate for
missing or invalid evidence with larger prompts, more model iterations, or
fabricated defaults.

## 6. Batch and composite operations

Prefer operational/composite capabilities over model-mediated chains of atomic
calls. Execute independent evidence nodes in parallel under the shared budget.

## 7. Execution state and persistence

Discard command outputs, raw observations, DAG state, and runtime execution
context after an investigation. Persist only the implemented conversation
history/summary and the bounded semantic `SessionInvestigationContext`. Cache
reuse follows freshness and validity policy and never turns failed, partial, or
stale evidence into success.

## 8. Simplicity

Prefer small functions, explicit names, readable deterministic code, and
incremental patches. Do not introduce a factory, strategy, repository, plugin
system, event bus, middleware, or service locator unless a concrete current
problem requires it.

## 9. Compatibility

Preserve public interfaces, API response fields, capability names, data
formats, and supported configuration unless the task explicitly changes them.
Compatibility adapters must remain explicit and tested.

## 10. Dependencies

Prefer the standard library. Every imported third-party runtime dependency
must be declared in `pyproject.toml`; add dependencies only with technical
justification.

## 11. Credentials and transport security

Never hardcode credentials, tokens, passwords, private keys, or deployment
URLs in source or tracked registry metadata. Packaged Grafana/Zabbix secrets
belong in `/etc/orion/tool-credentials.json`. Treat any exposed secret as
compromised and rotate it.

SSH host-key verification is enabled by default. A target-level
`strict_host_key_checking: false` value is an explicit trusted-network
exception and must not become a global default.

## 12. Deployment scope

Keep product behavior within the implemented local, single-operator runtime.
Docker Compose supplies loopback HTTP, API-key protection, PostgreSQL, and the
internal RAG service. Source mode supplies local FastAPI/Vite and SQLite. Do not
document or implement unapproved deployment modes.

## 13. Scope discipline

Modify only the requested area. Preserve existing behavior unless the request
requires a change. Avoid unrelated cleanup, generated-file edits, speculative
features, and silent requirement guesses.

## 14. Validation

Review `git diff` and `git status`. Run the smallest relevant local unit,
syntax, lint, or type checks for the changed area. Do not run smoke, E2E,
full-QA, Docker-based validation, benchmarks, or external-service tests unless
the current user request explicitly authorizes that class of validation.

The benchmark runner is relevant only when pipeline/model changes alter
scoring, prompts, or evidence collection. Documentation-only changes do not
require benchmarks.

## 15. Documentation

Active documentation describes only the current implementation. Do not add
roadmaps, backlogs, milestones, target architecture, proposed features, or
unfinished work. Historical delivery detail belongs in Git history or the
changelog, not in `08_PROJECT_STATE.md`.

## 16. Completion

A task is complete when the requested change is present, the diff contains no
accidental edits, appropriate permitted validation has succeeded, and the
final report states exactly which checks ran. Never claim unexecuted tests or
unverifiable behavior.
