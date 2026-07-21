# 09 - Architecture Decisions
Records long-term architectural decisions. Each entry: Decision, Context, Reason, Consequence. Do not put implementation details, TODOs, or roadmap items here — those belong in `04_ROADMAP.md` and `08_PROJECT_STATE.md`.
> A separate, narrative ADR set also exists at `docs/adr/` (e.g. `ADR-0001-agent-responsibility-boundary.md`, `ADR-0002-llm-assessment-only.md`, `ADR-0003-knowledge-tool-single-entry-point.md`, `ADR-0004-stateless-state-management.md`) for longer-form decision records. AD-002 is the short-form summary of ADR-0002, AD-003 of ADR-0003, AD-007 of ADR-0004, and AD-020 of ADR-0001; read the `docs/adr/` files for full context if needed. Numbering in `docs/adr/` is independent of the AD-### numbering here — do not assume they line up 1:1.
---
## AD-001 — Infrastructure investigation is deterministic
**Decision:** Investigation execution is deterministic wherever possible.
**Context:** Most infrastructure investigation follows repeatable operational procedures.
**Reason:** Deterministic execution is faster, cheaper, easier to benchmark, and more reliable than AI planning.
**Consequence:** Intent resolution, target resolution, evidence planning, capability selection, and execution scheduling all use deterministic code whenever possible.
## AD-002 — The language model performs assessment only
**Decision:** The LLM interprets evidence; it does not plan, execute, or access infrastructure.
**Context:** The LLM is best suited to interpreting evidence, not controlling execution.
**Reason:** Separating investigation from assessment reduces token usage and improves consistency.
**Consequence:** The model explains findings and generates recommendations. It never plans investigations, executes tools, or touches infrastructure directly.
> Long-form ADR: `docs/adr/ADR-0002-llm-assessment-only.md`
## AD-003 — KnowledgeTool is the single runtime entry point
**Decision:** `KnowledgeTool` is the only entry point for evidence collection.
**Context:** The platform supports multiple infrastructure domains (Linux, Grafana, Zabbix today; more later).
**Reason:** The assessment layer should never depend on domain-specific implementations.
**Consequence:** `KnowledgeTool` exposes capability metadata, routes requests, aggregates results. Child Tools stay hidden behind it.
> Long-form ADR: `docs/adr/ADR-0003-knowledge-tool-single-entry-point.md`
## AD-004 — Each Child Tool owns exactly one infrastructure domain
**Decision:** One domain per Child Tool, no overlap.
**Context:** Operational evidence should stay modular.
**Reason:** High cohesion → simpler maintenance, easier extension.
**Consequence:** `LinuxTool`, `GrafanaTool`, `ZabbixTool` today; any future domain (e.g. Docker, VMware) gets its own tool rather than being bolted onto an existing one.
## AD-005 — Capability definitions belong exclusively to Child Tools
**Decision:** One location owns each capability definition.
**Reason:** Capability metadata must stay synchronized and non-duplicated.
**Consequence:** Child Tools define capabilities; `KnowledgeTool` aggregates metadata; the Execution Engine consumes aggregated metadata only.
## AD-006 — Infrastructure is always the Source of Truth
**Decision:** Runtime always prefers live infrastructure over cached information.
**Reason:** Operational decisions must rely on current state, not stale snapshots.
**Consequence:** Snapshots/caches are optional and never replace live evidence.
## AD-007 — Execution remains stateless
**Decision:** Execution state is discarded after every completed investigation.
**Context:** Each investigation must be independent; see `docs/adr/ADR-0004-stateless-state-management.md` for full reasoning, including the Stable vs. Dynamic Information split.
**Reason:** Stateless execution reduces coupling and prevents stale operational decisions.
**Consequence:** Only summarized session knowledge may persist, never raw observations, tool outputs, or execution state.
> Long-form ADR: `docs/adr/ADR-0004-stateless-state-management.md`
## AD-008 — Session memory stores summaries only
**Decision:** No raw observations, tool outputs, execution state, or reasoning history in session memory.
**Reason:** Summaries reduce redundant execution without reintroducing implicit state; see `docs/adr/ADR-0004-stateless-state-management.md` for the Stable vs. Dynamic Information split that motivates this rule.
## AD-009 — Evidence quality outranks AI reasoning complexity
**Decision:** Tool → Evidence → Assessment is the improvement order; prompt engineering is secondary.
**Reason:** Improving deterministic evidence is a more reliable lever than increasing prompt complexity.
## AD-010 — Composite capabilities are preferred over atomic ones
**Decision:** Expose operational capabilities, not just low-level API wrappers.
**Reason:** Fewer iterations, smaller prompts, simpler planning.
## AD-011 — Execution should minimize model interaction
**Decision:** Batch, parallelize, and deterministically aggregate before requesting AI assessment.
**Reason:** LLM calls are the expensive, latency-heavy part of the pipeline.
## AD-012 — Dependencies remain strictly one-directional
**Decision:** `Assessment Model → Execution Engine → KnowledgeTool → Child Tool → Environment`. Reverse dependencies are prohibited.
**Reason:** Layered architecture keeps coupling low.
> Long-form ADRs: `docs/adr/ADR-0002-llm-assessment-only.md`, `docs/adr/ADR-0003-knowledge-tool-single-entry-point.md`
## AD-013 — Providers are optional infrastructure adapters
**Decision:** Only introduce a Provider layer when access complexity justifies it; simple environments may be accessed directly by Child Tools.
**Reason:** Avoid unnecessary abstraction (see `07_DEVELOPMENT_RULES.md`, rule 12).
## AD-014 — Architecture ownership belongs to the human reviewer
**Decision:** AI implements approved architecture; architectural changes always require explicit human approval.
**Reason:** Prevent uncontrolled architectural drift over a long-lived project.
## AD-015 — Repository state always overrides assumptions
**Decision:** Inspect the repository before implementing; repository contents override documentation, memory, or prior reasoning.
**Reason:** Documentation can go stale; the repository is the authoritative implementation. This is also why `08_PROJECT_STATE.md` exists as the single status source of truth.
## AD-016 — Platform evolution is incremental
**Decision:** Prefer small, benchmark-validated patches over large redesigns unless explicitly approved.
**Reason:** Small verified improvements are easier to validate and maintain in a long-lived project.
---
## AD-017 — SSH host key verification is intentionally disabled (current scope)
**Decision:** `LinuxTool`'s SSH execution backend uses `StrictHostKeyChecking=no` and `UserKnownHostsFile=/dev/null`.
**Context:** The Agent currently runs local-only, against infrastructure inside a trusted internal network (`02_CURRENT_ARCHITECTURE.md`).
**Reason:** This is a deliberate trade-off for the current trusted-network, single-operator scope — not an oversight. It avoids host-key friction when investigating many/ephemeral targets during local use.
**Consequence:** This setting is a real MITM exposure if the Agent ever executes SSH commands over an untrusted network. **This decision must be revisited before or during WP4** (`04_ROADMAP.md`), when the Agent starts running as a platform capability potentially reachable by multiple users/targets outside a single trusted local network. Do not silently "fix" this in the meantime (`07_DEVELOPMENT_RULES.md`, rule 17) — if it needs to change, that change gets its own AD entry.
## AD-018 — No credentials hardcoded in tool source code
**Decision:** Grafana/Zabbix tokens (or any secret) must never be hardcoded as default values or literals in `src/tool/*.py` or committed to the repository.
**Context:** A real Grafana service-account token and internal URL were previously found hardcoded as default parameter values in `grafana_tool.py`.
**Reason:** Hardcoded secrets in source are effectively public once the repository is shared, backed up, or committed to any remote — regardless of intent.
**Consequence:** Secrets must be supplied through a mechanism outside version control (current agreed mechanism recorded below once settled — env var / gitignored local config / OS credential store). The previously exposed Grafana token must be treated as compromised and rotated on the Grafana server, independent of the code fix. **Status of which supply mechanism is actually implemented: see `08_PROJECT_STATE.md`.**
## AD-019 — Local-first, platform-second sequencing
**Decision:** The project stays on the local architecture (`02_CURRENT_ARCHITECTURE.md`) until public VM access triggers `04_ROADMAP.md` WP1. The platform architecture (`03_PLATFORM_ARCHITECTURE.md`) is accepted as the long-term target but is not built speculatively ahead of that trigger.
**Reason:** Avoid building database/auth/API-server infrastructure with no environment to run it on yet, and avoid diverging effort from the working local tool.
**Consequence:** Any work that assumes multi-user state, a database, or remote hosting is out of scope until `08_PROJECT_STATE.md` shows WP1 has started.
## AD-020 — Agent is an execution engine, not a reasoning component
**Decision:** The Agent executes model-generated actions and returns raw observations; it never reasons, plans, generates commands, or analyzes results. All intelligence belongs to the reasoning model.
**Context:** The project originally explored an autonomous-agent architecture where the Agent would reason and plan independently.
**Reason:** Separating execution from reasoning keeps the Agent deterministic, predictable, and model-agnostic. The reasoning model can be swapped without changing the Agent.
**Consequence:** Architecture follows an Action → Observation loop. The Agent is a pure execution engine. New reasoning models can replace existing ones without modifying the Agent.
> Long-form ADR: `docs/adr/ADR-0001-agent-responsibility-boundary.md`
