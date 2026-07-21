# 07 - Development Rules
These rules are mandatory for all work performed in this repository. If implementation convenience conflicts with these rules, the rules take precedence. This file is the highest-priority document after `00_BOOTSTRAP.md` (see conflict priority there).
## 1. Development Goals
Prioritize: deterministic execution, evidence quality, simplicity, maintainability, extensibility, token efficiency, benchmarkability. Avoid unnecessary complexity. The platform should become more capable by improving deterministic execution rather than increasing AI reasoning.
## 2. Architecture is Authoritative
The approved architecture (`02_CURRENT_ARCHITECTURE.md`, and `03_PLATFORM_ARCHITECTURE.md` once WP1+ is underway) is the source of truth. Do not modify responsibilities, dependencies, ownership, or architectural boundaries without explicit approval. Architecture changes require context, motivation, trade-off analysis, and impact analysis. Implementation must never change architecture implicitly.
## 3. Deterministic Before AI
Prefer deterministic logic wherever it can solve the problem: intent routing, target resolution, evidence planning, capability selection, result aggregation, severity calculation, threshold evaluation. Do not introduce AI reasoning where deterministic execution is sufficient.
## 4. Single Responsibility
| Component | Responsibility |
|---|---|
| Assessment Model | Evidence interpretation |
| Execution Engine | Investigation execution |
| KnowledgeTool | Capability routing |
| Child Tool | Evidence collection |
| Environment | Source of Truth |
Responsibilities must never overlap.
## 5. Evidence First
Preferred order: Better Tool → Better Evidence → Better Assessment. Do not compensate poor evidence with larger prompts, more iterations, or more AI reasoning.
## 6. Composite Before Atomic
Prefer `assess_machine()` over requiring callers to chain `cpu()`, `memory()`, `disk()`, `network()`, `service()` independently — reduces token usage, iterations, planning complexity.
## 7. Batch Before Loop
Execute independent evidence requests together (parallel), not as a tool → LLM → tool → LLM loop. Minimize investigation iterations.
## 8. Stateless Execution
Execution state exists only during a single investigation. Never persist execution state, observations, tool outputs, or runtime context beyond that — except where `03_PLATFORM_ARCHITECTURE.md` explicitly introduces persistent Agent history in the platform Database (WP4). The `PostgresConversationStore` (WP4 in progress) persists conversation history (summaries only, not raw observations) — this is the only exception to the stateless rule and should not be treated as a precedent for storing execution state.
## 9. Child Tools & 10. Capability Design
See `06_TOOL_AND_CAPABILITY_DESIGN.md` — the full contract for Child Tools, capabilities, and KnowledgeTool lives there, not duplicated here.
## 11. Coding Principles
Prefer small functions, explicit naming, readable code, deterministic logic, incremental patches. Avoid unnecessary abstraction.
## 12. No Over-Engineering
Do not introduce Factory, Strategy, Repository Pattern, Plugin System, Event Bus, Middleware, or Service Locator patterns unless an actual implementation problem requires them.
## 13. Repository First
Before changing code: understand the repository, reuse existing implementations, extend existing abstractions, avoid duplicate implementations. Never create parallel solutions.
## 14. Backward Compatibility
Do not break public interfaces, capability outputs, APIs, or data formats without explicit approval. Backward compatibility is the default.
## 15. Dependencies
Prefer the Python standard library. Do not introduce external dependencies unless technically justified and approved. Any dependency that is actually used must be declared in `pyproject.toml` — an empty `dependencies = []` while the code imports third-party packages is a rule violation, not a style choice.
## 16. Credential and Secret Handling
No credential, token, password, or API key may be hardcoded in source code, as a default parameter value, or committed to the repository — including in tool files like `grafana_tool.py` / `zabbix_tool.py`. Secrets live outside version control (gitignored config, environment variable, or OS credential store, per the current agreed mechanism — see `09_ARCHITECTURE_DECISIONS.md` for which one is in effect). If a secret is ever found hardcoded in a file that may have been committed or shared, treat it as compromised and flag it for rotation — do not just delete it silently.
## 17. Intentional Security Trade-offs Must Be Documented, Not Silently Changed
Some security-relevant defaults are intentional for the current local, trusted-network scope (e.g. SSH host key checking currently disabled — see `09_ARCHITECTURE_DECISIONS.md`). Do not "fix" these unilaterally. If a trade-off looks wrong, raise it — do not change it without recording the decision (or its reversal) in `09_ARCHITECTURE_DECISIONS.md`.
## 18. Local Scope Until the Roadmap Says Otherwise
The project runs local today (`02_CURRENT_ARCHITECTURE.md`). A PostgreSQL session store and optional API key auth are implemented for the `--web` mode. Do not add multi-user accounts, remote hosting, or production deployment speculatively — that work is sequenced in `04_ROADMAP.md` WP1 and only begins once public VM access is available.
## 19. Implementation Mode
Unless explicitly requested otherwise, operate in Implementation Mode: implement approved designs, preserve existing behavior, avoid unrelated refactoring, keep patches small, stop after the scoped task. Architecture discussion happens only when explicitly requested.
## 20. Implementation Rules
Modify only the approved scope. Avoid speculative features, APIs, or workflows. Preserve existing behavior unless required otherwise. Never guess missing requirements — ask or state the assumption explicitly instead.
## 21. Verification Before Every Commit
Review implementation, verify responsibilities/dependencies/architecture boundaries, run affected tests, run affected benchmarks when behavior changes, review `git diff` and `git status`. Resolve regressions before committing.
## 22. Definition of Done
A task is complete only when: implementation is complete, tests pass (when tests exist for the touched area), benchmarks pass when applicable, no regressions remain, architecture remains intact, the repository is clean, and it's one logical change per commit.
## 23. Benchmark-Driven Development
New capabilities should exist because a benchmark scenario requires additional evidence — not because they appear useful. Benchmark quality matters more than implementation quantity. (Current status: benchmark runner exists at `benchmark/` — see `08_PROJECT_STATE.md`.)
## 24. Capability Metadata — One Source of Truth
Child Tools define capabilities. KnowledgeTool aggregates metadata. The Execution Engine consumes metadata. Capability definitions must never be duplicated.
## 25. Reporting — Never Claim Undone Work as Done
Never report planned work as completed. Completed work must be verifiable through `git diff`, `git status`, test results, or benchmark results. Claims without evidence are not considered complete. This applies to `08_PROJECT_STATE.md` above all — that file must always reflect what is actually verifiable in the repository, not aspirational status.
## 26. Final Principle
Whenever uncertain, choose the simpler solution. Priority order: Evidence → Deterministic Execution → Architecture → Correctness → Maintainability → Performance → Convenience. Simple solutions are preferred until benchmark results prove otherwise.
