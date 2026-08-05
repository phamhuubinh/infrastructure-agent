# Orion Implementation Backlog

> **Historical implementation plan and completed work record, retained as a static reference.**
> The current, single active backlog is `docs/project/DETERMINISTIC_REASONING_BACKLOG.md` (see `docs/project/README.md`). Current implementation status lives in `docs/ai/08_PROJECT_STATE.md`.

> **Source Documents Merged:**
> - `FINAL_ARCHITECTURE_REVIEW.md` (FAR) — Principal Architect review across 5 projects
> - `ARCHITECTURE_CRITIQUE.md` (AC) — Peer critique with source-code verification
> - `orion_improvements_ranked.md` (OIR) — Original 10 recommendations + Principal Architect critique
>
> **Methodology:**
> - All quantitative claims in FAR were corrected per AC's source-code verification (Hermes LOC, module counts, service file sizes).
> - Duplicate recommendations across documents were merged into single items.
> - Conflicting recommendations were resolved by favoring the recommendation with stronger technical justification or explicit ADR alignment.
> - The Orion source code at `/home/binh/projects/Orion_agent/` was used as ground truth for verification.
> - No source code was modified.
>
> **Date:** 2026-07-26

---

## 1. Deduplication and Conflict Resolution

### 1.1 Items Already Present in Orion

Three recommendations from OIR were verified as already existing and are **excluded** from the backlog:

| Original Recommendation | Why Excluded |
|-------------------------|--------------|
| Intent-Aware Prompt Templates (#4 in OIR) | `prompt_builder_v2.py` (368 LOC) has 11 intent-specific prompts, evidence summarization, normalization, language detection, and version switching. Gap: prompts are hardcoded Python strings. Downgraded to refactoring item (#7 below). |
| Context Management / Summarization (#7 in OIR) | `conversation_store.py` (286 LOC) has LLM-based summarization with structured prompt, incremental merge, auto-trigger at configurable threshold. Adequate for Orion's 3-10 turn sessions. |
| Cross-Session Evidence Caching (#10 in OIR) | `evidence_cache.py` (69 LOC) has TTL-based per-session caching. Cross-session persistence is a modest enhancement, not a backlog item. |

### 1.2 Duplicates Merged

| Duplicate Pair | Resolution |
|---------------|------------|
| FAR "Configuration Schema Validation" (#1) = OIR "Configuration Validation" (#5) = AC confirmed | Single item (#2 below). FAR's Pydantic-model recommendation adopted. |
| FAR "Multi-Provider LLM Support" (#3) = OIR "Multi-Provider LLM + Failover" (#3) = AC confirmed | Single item (#8 below). FAR's AssessmentModelAdapter approach adopted. |
| FAR "Capability-Level Security Pipeline" (#2) = OIR "Security/Safety Pipeline" (#2) = AC confirmed with scope adjustment | Single item (#4 below). AC's scope adjustment (cover chat() path) incorporated. |
| FAR "Tool Auto-Discovery" (#5) = OIR Plugin System (#1, demoted) = AC notes `_SUPPORTED_TOOL_TYPES` already IS a registry | Auto-discovery retained (#5), full plugin system deferred (#13). |
| FAR "Retry Policy" (#6) = AC "retry exists but no unified abstraction" | Reframed as Retry Policy Unification (#6). |
| FAR "Scattered Configuration" (weakness #6) = AC "11 config sources, not 6" = OIR not listed | New item: Unified Configuration Accessor (#3). |

### 1.3 Conflicts Resolved

| Conflict | Resolution | Rationale |
|----------|-----------|-----------|
| FAR: SQLite REJECT vs. AC: SQLite ROADMAP (replace JSON) vs. OIR: SQLite Priority 6 | **ROADMAP with condition** (replace JSON, not add third backend) | AC's argument is correct: replacing JSON with SQLite reduces backends from 2 to 1 for single-user deployments. FAR's rejection was based on "adding a third backend" — AC reframed this correctly. |
| FAR: Streaming ROADMAP vs. AC: REMOVE from ranked list vs. OIR: Streaming Priority 4 | **EXCLUDED from backlog** | AC's argument is conclusive: for a 1-5 second pipeline, `run_with_steps()` structured output is better UX than streaming. Streaming adds framing overhead without meaningful benefit. |
| FAR/OIR: Plugin Priority disagreement (OIR #1 → demoted by FAR) | **EXCLUDED from immediate backlog, retained as horizon item** | FAR's analysis is correct: Orion is a vertical tool with a bounded domain. A plugin system (800-1200 LOC) is disproportionate to the benefit. |
| FAR: Unified Frontend Protocol ROADMAP vs. OIR: Priority 7 | **EXCLUDED from backlog, deferred** | Both documents agree this is strategic investment only needed when adding a fourth frontend. |

### 1.4 New Items from Architecture Critique

Three items identified by AC were missing from both OIR and FAR. They are included because they represent genuine architectural risks verified against source code:

| New Item | Source | Rationale |
|----------|--------|-----------|
| ADR-0001 Reconciliation | AC §2.1 | ADR-0001 describes a model-driven iterative loop; implementation is a deterministic pipeline. This is the single largest architectural documentation risk. |
| RAG Subsystem Rationalization | AC §4.3 | The LangGraph-based RAG subsystem embeds a framework dependency that contradicts FAR's "don't adopt LangGraph" stance. |
| Unified Configuration Accessor | AC §2.5 | AC verified 11 config sources (vs. FAR's count of 6). Fragmentation is worse than FAR identified. |

### 1.5 Final Item List

| # | Item | Priority | Category | Source Documents |
|---|------|----------|----------|-----------------|
| 1 | ADR-0001 Reconciliation | P0 | Foundation | AC (new) |
| 2 | Configuration Schema Validation (Pydantic) | P0 | Quick Win | FAR #1, OIR #5, AC ✓ |
| 3 | Unified Configuration Accessor | P0 | Foundation | FAR weakness #6, AC §2.5 |
| 4 | Capability-Level Security Pipeline | P1 | Foundation | FAR #2, OIR #2, AC §7.2 |
| 5 | Tool Auto-Discovery / Simplified Registration | P1 | Refactor | FAR #5, OIR plugin (partial), AC §5.3 |
| 6 | Retry Policy Unification | P1 | Foundation | FAR #6, AC §1.4 |
| 7 | Prompt Template Extraction | P2 | Refactor | FAR #4, OIR ✓ (moved from "exists" to refactoring) |
| 8 | Multi-Provider LLM Support with Failover | P2 | Foundation | FAR #3, OIR #3, AC §7.2 |
| 9 | Immutable Pipeline State | P2 | Refactor | FAR weakness #4, AC §6.3 |
| 10 | RAG Subsystem Rationalization | P3 | Refactor | AC §4.3 (new) |
| 11 | SQLite as Default Persistence (Replace JSON) | P3 | Future | FAR "REJECT", AC "ROADMAP", OIR #6 |
| 12 | Configuration Error Handling Policy | P3 | Foundation | AC §6.2 (new) |
| 13 | Plugin/Extension System | Horizon | Future | FAR ROADMAP, OIR #1 (demoted), AC §3.2 |

---

## 2. Detailed Item Descriptions

---

### Item 1: ADR-0001 Reconciliation

**Problem Statement:**
ADR-0001 ("Agent is an execution engine") describes a model-driven iterative architecture: *"The reasoning model decides whether to continue execution or produce the final answer... Execution becomes an iterative Action → Observation loop."* The current implementation (`deterministic_agent.py`, 648 LOC) is a deterministic single-pass pipeline with an 8-condition `_should_pipeline()` routing decision tree. ADR-0002 was written *after* this shift and documents the constraint that the LLM is used only for assessment. ADR-0001 was never updated.

This divergence means future developers reading ADR-0001 will believe the Agent should be driven by model decisions about "whether to continue execution." If someone implements ADR-0001 literally, they will build a ReAct loop — exactly the architecture Orion intentionally rejected. ADR-0001 currently describes an architecture that does not exist in the codebase.

**Expected Benefit:**
- Eliminates the single largest architectural documentation risk.
- Prevents future contributors from building against incorrect architectural documentation.
- Clarifies the design evolution from model-driven (ADR-0001 original) to deterministic pipeline (ADR-0002 + implementation).
- Ensures all future backlog items (multi-provider, security pipeline, etc.) are designed against the correct architecture.

**Implementation Complexity:** Low (documentation-only change, ~100 LOC of ADR text).

**Architectural Risk:** None. This is a documentation correction, not a code change.

**Maintenance Cost:** None. Reduces maintenance burden by eliminating misleading documentation.

**Dependencies:** None.

**Affected Modules:**
- `docs/adr/0001-agent-as-execution-engine.md` — Requires SUPERSEDED notice or full rewrite.
- `docs/adr/0002-llm-for-assessment-only.md` — May need cross-reference update.
- Potentially a new ADR documenting the deterministic pipeline architecture (the 6-stage pipeline, 8-condition `_should_pipeline()` routing).

**ADR Impact:**
- ADR-0001: Add SUPERSEDED banner pointing to ADR-0002 and the new pipeline ADR.
- ADR-0002: Add note clarifying it supersedes ADR-0001's execution model description.

**Recommended Benchmark:** Not applicable (documentation change).

---

### Item 2: Configuration Schema Validation (Pydantic Models)

**Problem Statement:**
Orion loads configuration from multiple JSON/YAML files without schema validation. Invalid configurations (wrong types, missing required fields, invalid enum values) surface as runtime errors deep in the pipeline. Examples from source code:
1. `_build_assessment_adapter()` casts config values with `int()` and `float()` — a non-numeric config value causes a runtime crash.
2. `runtime_factory.py` line 309 accesses `tools_config.get("tools", [])` but `tools_config` is built from a flat dict of tool entries — the `"tools"` key doesn't exist, so `len()` always returns 0.
3. `_load_server_config()` raises `RuntimeError` if `servers.json` is missing but `_load_tools_config()` silently returns `{}` if `tools.json` is missing.

The lack of a configuration schema means the system's configuration contract is implicit and unenforceable.

**Expected Benefit:**
- Catches configuration errors at startup instead of mid-pipeline.
- Enables IDE autocompletion for configuration files (via JSON Schema generation from Pydantic).
- Documents the configuration contract explicitly.
- Prevents the class of bugs where invalid config silently produces wrong behavior.

**Implementation Complexity:** Low (100-150 LOC).
- Pydantic models for `servers.json`, `tools.json`, `targets.json`.
- Validation at FastAPI app startup and CLI entry point.
- JSON Schema export for IDE integration.

**Architectural Risk:** Very Low. Validation is additive — stricter. Invalid config that previously failed silently (e.g., wrong type) becomes an explicit error.

**Maintenance Cost:** Low. Pydantic models evolve alongside config structure. Schema changes are explicit and versioned.

**Dependencies:** None. Pydantic is already in the project's dependency tree (via FastAPI).

**Affected Modules:**
- `config/servers.json` → `PydanticServerConfig`
- `config/tools.json` → `PydanticToolConfig`
- `config/targets.json` → `PydanticTargetConfig`
- `src/backend/app.py` — validate at startup
- `src/cli/main.py` — validate at CLI entry
- `src/agent/runtime_factory.py` — replace ad-hoc type casting with validated model access

**ADR Impact:** None. Purely additive validation.

**Recommended Benchmark:** Startup validation test suite — verify each config file with valid and invalid variants.

---

### Item 3: Unified Configuration Accessor (`OrionConfig`)

**Problem Statement:**
Configuration is spread across 11 sources (verified by AC against `runtime_factory.py` and `deterministic_agent.py`):
1. `servers.json`
2. `tools.json`
3. `targets.json`
4. External tool credentials (`/etc/orion/tool-credentials.json` by default)
5. `config/conversational_patterns.yaml`
6. `config/capability_plans.yaml`
7. `config/concepts.yaml`
8. `config/target_aliases.yaml`
9. Environment variables (`ORION_*`)
10. `_VAGUE_HEALTH_PATTERNS` hardcoded class attribute
11. `_conv_vi_patterns` / `_conv_en_patterns` loaded from YAML with fallback defaults

There is no unified accessor. Each module reads its own config sources via scattered `os.environ.get()` calls and JSON file reads. This creates a discoverability problem — new users and developers cannot determine where a setting is configured. It also makes it impossible to validate the complete configuration at startup (Item #2 depends on this).

**Expected Benefit:**
- Single source of truth for all configuration access.
- Enables startup validation of the complete configuration (prerequisite for Item #2).
- Simplifies testing (mock a single `OrionConfig` instead of multiple files + env vars).
- Enables configuration documentation generation.
- Enables configuration diff/drift detection.

**Implementation Complexity:** Medium (200-300 LOC).
- `OrionConfig` dataclass/pydantic model that aggregates all config sources.
- `OrionConfig.load()` method that reads all sources with consistent error handling.
- Replace scattered `os.environ.get()` calls with `config.xxx` attribute access.
- Deprecation warnings for direct config file reads outside the accessor.

**Architectural Risk:** Low-Medium. Touches many modules. Migration must be incremental — support both old (direct reads) and new (accessor) during transition, then remove old paths.

**Maintenance Cost:** Medium (initial migration). Low (ongoing — single config access point).

**Dependencies:** Item #2 (Pydantic models). The unified accessor uses the Pydantic models for validation.

**Affected Modules:**
- New: `src/shared/config.py` — `OrionConfig` class
- `src/agent/runtime_factory.py` — migrate config reads
- `src/agent/deterministic_agent.py` — migrate env var reads
- `src/backend/app.py` — migrate config reads
- `src/cli/main.py` — migrate config reads
- `src/pipeline/intent_resolver.py` — migrate `_VAGUE_HEALTH_PATTERNS`
- `src/model/protocol/prompt_builder_v2.py` — migrate language detection config

**ADR Impact:** May warrant a new ADR documenting the unified configuration architecture.

**Recommended Benchmark:** Configuration load time (must not increase by >10%). Coverage of all 11 config sources in the accessor.

---

### Item 4: Capability-Level Security Pipeline

**Problem Statement:**
Orion has zero runtime safety checks. `KnowledgeTool.execute()` dispatches directly to child tools via `_dispatch()`. The `chat()` method in `DeterministicAgent` bypasses `KnowledgeTool` entirely — it calls `self._assessment_model.assess_raw(prompt)` directly, creating a naked LLM call path with no capability validation, no tool dispatch, and no security checks.

The current safety comes from limitation (capabilities happen to be read-only monitoring functions), not from design (the architecture enforces read-only). If a new capability that modifies system state is added, nothing in the architecture prevents or flags it. The `chat()` path provides an unguarded LLM interaction mode with no security boundaries.

The comparison projects all have security layers (Goose: 5-layer inspection pipeline, OpenHands: SecurityAnalyzer + sandbox, Hermes: guardrails + threat scanning). Orion's static capability registry means it doesn't need Goose's 5-layer model, but it does need architectural enforcement of its safety guarantees.

**Expected Benefit:**
- Architectural guarantee of read-only execution (not just "currently happens to be read-only").
- Target validation — prevent calling production tools against development targets.
- Audit trail for all tool executions.
- Security coverage for both pipeline path (`KnowledgeTool._dispatch()`) and chat path (`assess_raw()`).
- Fulfills ADR-0001's safety obligation: "Agent is responsible for 'enforcing execution safety'."

**Implementation Complexity:** Medium (200-300 LOC).
- `ToolInspector` ABC with Allow/Deny/RequireApproval return type.
- `ReadOnlyInspector` — validates capability handlers don't mutate state.
- `TargetInspector` — validates tool is called against an expected target.
- `ParameterSafetyInspector` — validates parameters against dangerous patterns.
- Insert inspector chain in `KnowledgeTool._dispatch()` path.
- Add guard in `DeterministicAgent.chat()` to prevent dangerous prompts.

**Architectural Risk:** Low. Additive. Default-allow for existing capabilities during transition. Inspector chain can be bypassed via config flag during development.

**Maintenance Cost:** Low-Medium. Inspector chain is extensible (add new inspectors without modifying existing ones). Each inspector is independently testable.

**Dependencies:** None, but Item #5 (Tool Auto-Discovery) should route through the same inspector chain.

**Affected Modules:**
- New: `src/pipeline/security/` — `ToolInspector` ABC, `ReadOnlyInspector`, `TargetInspector`, `ParameterSafetyInspector`
- `src/tool/knowledge_tool.py` — insert inspector chain in `_dispatch()`
- `src/agent/deterministic_agent.py` — add guard in `chat()` method
- `src/shared/capability.py` — add `mutation_risk` field to `Capability` dataclass

**ADR Impact:** May warrant a new ADR documenting the security model. ADR-0001's safety obligation is partially fulfilled by this item.

**Recommended Benchmark:**
1. Inspector chain latency (must add <5ms per tool call).
2. Coverage: all registered capabilities must pass through inspector chain.
3. Regression: existing capabilities must not be blocked by default.

---

### Item 5: Tool Auto-Discovery / Simplified Registration

**Problem Statement:**
Adding a new tool currently requires 4 steps across 3+ files:
1. Create `Tool` subclass with `_CAPABILITIES` dict.
2. Add to `_SUPPORTED_TOOL_TYPES` dict in `runtime_factory.py`.
3. Add construction block in `_register_single_tool()`.
4. Register in `targets.json` / `tools.json`.

The AC correctly notes that `_SUPPORTED_TOOL_TYPES` already IS a lightweight plugin registry — new tools are configured in JSON (not hardcoded), tool loading validates required fields, and failed registration doesn't crash the system. The gap is steps 2-3: the factory needs explicit knowledge of every tool type.

Auto-discovery of `Tool` subclasses that declare `_CAPABILITIES` would reduce registration from 4 steps to 1 (create the file).

**Expected Benefit:**
- Reduces adding a tool from 4 steps to 1 (create the file with `_CAPABILITIES`).
- Eliminates the factory's explicit knowledge of tool types.
- Enables tools to be added via pip packages (future: entry points discovery).
- Reduces risk of merge conflicts when multiple developers add tools.

**Implementation Complexity:** Medium (150-250 LOC).
- `ToolRegistry` that scans `tool/` subdirectories for `Tool` subclasses with `_CAPABILITIES` attribute.
- Auto-registration during agent construction.
- Backward-compatible with existing factory registration.
- Entry point discovery for external packages (pip-installed tools).

**Architectural Risk:** Low. Backward-compatible. Existing registration path preserved during transition. Auto-discovery is additive.

**Maintenance Cost:** Low. Registration ceremony elimination reduces maintenance (no more updating `_SUPPORTED_TOOL_TYPES` and `_register_single_tool()` for each new tool).

**Dependencies:** Item #4 (Security Pipeline). Auto-discovered tools must pass through the inspector chain.

**Affected Modules:**
- New: `src/tool/registry.py` — `ToolRegistry` with auto-discovery
- `src/agent/runtime_factory.py` — integrate auto-discovery alongside existing registration
- `src/tool/` subdirectories — tools self-register via `_CAPABILITIES` module attribute

**ADR Impact:** None. Tool selection remains deterministic via `CapabilityPlanner`. Only registration method changes.

**Recommended Benchmark:** Tool registration time (must not increase by >20%). Coverage: all existing tools must be discoverable via auto-discovery.

---

### Item 6: Retry Policy Unification

**Problem Statement:**
FAR claimed "No built-in retry." AC verified that retry *does* exist, distributed across multiple pipeline stages:
- `src/pipeline/execution_plan.py` — retry in execution plan
- `src/pipeline/execution_graph.py` — retry in graph execution
- `src/pipeline/target_resolver.py` — retry in target resolution
- `src/backend/db.py` — retry in database operations
- `src/tool/RAGTool/app/agent/langgraph_agent.py` — retry in RAG agent
- `src/cli/main.py` — retry in CLI

The actual gap is the **lack of a unified retry abstraction** — each component implements retry independently, with different backoff strategies, retry counts, and error classification. The `ExecutionRuntime` has a global timeout (default 120s) but no per-node retry with configurable backoff. Infrastructure tools are inherently flaky (network timeouts, API rate limits, transient errors) — a consistent retry strategy is an architectural requirement, not a feature.

**Expected Benefit:**
- Consistent retry behavior across all pipeline stages.
- Configurable per-node retry with exponential backoff and jitter.
- Eliminates duplicated retry logic (6+ independent implementations).
- Improves reliability for flaky infrastructure tools (transient network errors, API rate limiting).

**Implementation Complexity:** Low-Medium (100-150 LOC).
- `RetryPolicy` dataclass: `max_attempts`, `backoff_base`, `backoff_max`, `jitter`, `retryable_exceptions`.
- `RetryExecutor` that wraps tool calls with retry logic.
- Integrate into `ExecutionRuntime.execute()`.
- Replace distributed retry implementations with centralized policy.

**Architectural Risk:** Low. Additive. Only affects failed tool calls. Existing retry logic in pipeline stages preserved during migration.

**Maintenance Cost:** Low. Centralized retry logic is easier to tune and debug than 6+ distributed implementations.

**Dependencies:** None.

**Affected Modules:**
- New: `src/pipeline/retry.py` — `RetryPolicy`, `RetryExecutor`
- `src/pipeline/execution_runtime.py` — integrate `RetryExecutor`
- `src/pipeline/execution_plan.py` — replace distributed retry with centralized
- `src/pipeline/execution_graph.py` — replace distributed retry
- `src/pipeline/target_resolver.py` — replace distributed retry
- `src/backend/db.py` — replace distributed retry

**ADR Impact:** None.

**Recommended Benchmark:** Pipeline execution time with retry (must not increase by >10% for successful first-attempt calls). Retry success rate on flaky endpoints (must improve).

---

### Item 7: Prompt Template Extraction

**Problem Statement:**
Prompts are embedded as hardcoded Python strings in `prompt_builder_v2.py` (368 LOC) and `deterministic_agent.py`. This couples prompt engineering to code changes — a prompt iteration requires a code deployment. The comparison projects (OpenHands, Goose, Hermes) all separate prompts from code via Jinja2 templates, external files, or user overrides.

However, Orion's prompts have genuine strengths that must be preserved:
- 11 intent-specific prompts (CPU, MEMORY, DISK, NETWORK_SINGLE, PROCESS, SERVICE, TROUBLESHOOTING, APPLICATION, MONITORING, PERFORMANCE, SECURITY).
- `_summarize_evidence()` — domain-specific field extraction per evidence type.
- `_normalize_evidence()` — truncation rules (lists >5 items, strings >300 chars).
- `_detect_language()` — Vietnamese character pattern matching with bilingual enforcement.
- Output format enforcement (`NEVER wrap in JSON or code blocks`).

**Expected Benefit:**
- Separates prompt engineering from code — prompt iteration without code deployment.
- Enables non-developer contribution to prompt improvements.
- Enables A/B testing of prompt variants.
- Preserves all existing prompt strengths (intent-specific structure, evidence summarization, bilingual support).

**Implementation Complexity:** Low-Medium (150-200 LOC).
- Extract 11 intent-specific prompts to `.j2` files.
- `PromptLoader` that reads templates and renders with Jinja2.
- Preserve `_summarize_evidence()` and `_normalize_evidence()` as Python functions invoked before template rendering.
- Preserve `_detect_language()` for bilingual prompt selection.
- Maintain `set_prompt_version()` for compact/minimal toggle.

**Architectural Risk:** Very Low. Prompts are already stable strings. Externalization doesn't change content.

**Maintenance Cost:** Low. Template files are easier to diff and review than embedded Python strings.

**Dependencies:** None.

**Affected Modules:**
- New: `config/prompts/` — `.j2` template files
- New: `src/model/protocol/prompt_loader.py` — Jinja2 rendering
- `src/model/protocol/prompt_builder_v2.py` — replace hardcoded strings with template loading
- `src/agent/deterministic_agent.py` — replace chat system prompt with template reference

**ADR Impact:** None. Prompt content is unchanged; only storage location changes.

**Recommended Benchmark:** Prompt rendering time (must not increase by >5%). Assessment quality regression test against existing benchmark suite.

---

### Item 8: Multi-Provider LLM Support with Failover

**Problem Statement:**
`LLMClient` supports only OpenAI-compatible endpoints with a single server configuration. No failover, no multi-provider abstraction, no credential pool. ADR-0001 states the architecture should be "model-agnostic" — the `AssessmentModelAdapter` ABC exists (with two implementations: `LLMAssessmentAdapter` and `MockAssessmentAdapter`), proving the abstraction works. But only one production implementation exists.

The investigation `classify()` path is deterministic after DR1-301; the `chat()` and post-evidence assessment paths still use the same single provider. Production deployments need redundancy. Air-gapped deployments need local models. Cost optimization needs provider choice.

**Expected Benefit:**
- Production redundancy via provider failover chain.
- Air-gapped deployment support via local models (Ollama, vLLM).
- Cost optimization (route simple queries to cheaper models, complex assessments to premium models).
- Fulfills ADR-0001's model-agnostic goal.
- `MockAssessmentAdapter` already proves the ABC works — adding a second production implementation validates the abstraction.

**Implementation Complexity:** Medium (200-400 LOC).
- `ProviderRegistry` mapping provider names to `AssessmentModelAdapter` implementations.
- `CredentialPool` for multi-key provider support.
- `FallbackChain` with configurable fallback order.
- Provider-specific prompt formatting in each adapter implementation.
- Anthropic adapter as second implementation (proves ABC with different provider family).

**Architectural Risk:** Low-Medium.
- Provider-specific prompt formatting quirks — each provider has different prompt-following characteristics.
- Token counting differs per provider (affects context window management).
- **Mandatory gate:** benchmark validation per provider. New provider must achieve ≥90% of current provider's assessment quality score.

**Maintenance Cost:** Medium. Each new provider adds an adapter implementation. Provider-specific prompt tuning must be maintained.

**Dependencies:**
- Item #2 (Configuration Schema Validation) — provider config must be validated.
- Item #7 (Prompt Template Extraction) — strongly recommended prerequisite; template-based prompts are easier to tune per provider.

**Affected Modules:**
- New: `src/model/providers/` — `ProviderRegistry`, `CredentialPool`, `FallbackChain`
- New: `src/model/providers/anthropic_adapter.py` — second `AssessmentModelAdapter` implementation
- `src/model/assessment_model_adapter.py` — may need `assess_raw()` signature refinement
- `src/model/llm_client.py` — refactor to support multiple providers
- `src/agent/runtime_factory.py` — integrate provider registry
- `config/servers.json` — extend schema for multiple providers

**ADR Impact:** Fulfills ADR-0001's model-agnostic claim. May warrant an ADR amendment documenting provider abstraction.

**Recommended Benchmark:**
1. Assessment quality score per provider (must achieve ≥90% of baseline).
2. Provider failover latency (must switch within timeout).
3. Prompt adherence per provider (bilingual prompt following, output format enforcement).

---

### Item 9: Immutable Pipeline State

**Problem Statement:**
The `InvestigationRequest` object is mutated in-place through all pipeline stages. Each stage adds fields (`intent`, `target`, `evidence_requirements`, `capability_references`, `execution_plan`, `execution_graph`, `evidence`, etc.) to the same mutable object. This creates temporal coupling — a stage's output depends on which previous stages have run.

Worse, `_build_pipeline_steps()` accesses `investigation.execution_plan.steps` without null-checking `execution_plan`. If `ExecutionPlanner` fails or pipeline stage order changes, this crashes with `AttributeError`. The pipeline stages have an **implicit interface contract** — each stage must populate specific fields, but there's no enforcement mechanism.

LangGraph's immutable state updates (nodes return partial state dicts, channels merge them) provide better separation of concerns. Orion doesn't need LangGraph's complexity, but adopting immutable state accumulation would improve testability and robustness.

**Expected Benefit:**
- Pipeline stages become independently testable (each stage returns its additions, no shared mutable state).
- Eliminates temporal coupling — stages can be reordered without breaking downstream stages.
- Null-safety — downstream stages can check whether a required field was populated.
- Enables pipeline stage parallelism (if two stages don't depend on each other's output, they can run concurrently).

**Implementation Complexity:** Medium (200-300 LOC).
- `PipelineState` immutable dataclass replacing mutable `InvestigationRequest`.
- Each pipeline stage returns a `StateUpdate` dict (partial state additions).
- `PipelineEngine` merges updates between stages.
- Downstream stages access state via typed accessors with null-checking.

**Architectural Risk:** Medium. Touches all pipeline stages. Must maintain backward compatibility with existing stage interface. Migration must be incremental — stages converted one at a time.

**Maintenance Cost:** Low (after migration). Immutable state is easier to reason about and debug. Stack traces become clearer (state at each stage is explicit).

**Dependencies:** None, but Item #3 (Unified Configuration Accessor) and Item #5 (Tool Auto-Discovery) would benefit from this being completed first.

**Affected Modules:**
- New: `src/shared/pipeline_state.py` — `PipelineState` dataclass
- `src/pipeline/` — all pipeline stages (normalizer, intent_resolver, tool_selector, evidence_planner, capability_resolver, capability_planner, execution_plan, execution_graph, execution_runtime)
- `src/agent/deterministic_agent.py` — `_build_pipeline_steps()` migration

**ADR Impact:** The deterministic pipeline architecture is unchanged. State management becomes explicit rather than implicit.

**Recommended Benchmark:** Pipeline execution time (must not increase by >5%). Pipeline stage test coverage (each stage must be independently testable after migration).

---

### Item 10: RAG Subsystem Rationalization

**Problem Statement:**
The `tool/RAGTool/app/agent/langgraph_agent.py` file embeds a LangGraph-based agent subsystem within Orion's tool layer. This creates an architectural inconsistency:

1. FAR correctly states Orion should not adopt LangGraph as a core pattern (LangGraph's BSP semantics, checkpoint architecture, and LLM-driven tool selection conflict with Orion's deterministic pipeline).
2. Yet the RAG subsystem uses `langgraph-core` as a dependency — importing a framework whose design philosophy contradicts Orion's.
3. The RAG subsystem has its own retry logic, agent loop, and state management — all patterns that Orion's ADRs intentionally reject.
4. The RAG subsystem is architecturally foreign to Orion's deterministic pipeline — it's an embedded general-purpose agent inside a deterministic tool.

The RAG *capabilities* (Qdrant vector store, BM25 sparse index, hierarchical chunking, HyDE query expansion, BGE reranker, OCR support) are genuine strengths. The issue is the *execution architecture* — LangGraph-based agent loop vs. deterministic pipeline.

**Expected Benefit:**
- Architectural consistency — all execution paths follow the deterministic pipeline model.
- Removes dependency on `langgraph-core` (reduces supply chain risk).
- Simplifies reasoning about system behavior (one execution model, not two).
- Potentially simpler RAG implementation using Orion's own `ExecutionRuntime` + DAG patterns.

**Implementation Complexity:** Medium-High (300-500 LOC).
- Audit RAG subsystem to identify LangGraph-specific vs. transport-agnostic components.
- Reimplement agent loop using Orion's deterministic pipeline patterns (or simplify to a direct retrieval pipeline).
- Vector store interaction (Qdrant), BM25, chunking, HyDE, BGE reranker — these are transport-agnostic and should be preserved.
- Remove `langgraph-core` dependency after migration.

**Architectural Risk:** Medium. RAG functionality must not regress. The LangGraph-based implementation may handle edge cases that a deterministic pipeline would need to explicitly address.

**Maintenance Cost:** Low (after migration). One less framework dependency to maintain and upgrade.

**Dependencies:** Item #9 (Immutable Pipeline State) — the RAG subsystem reimplementation would use the new pipeline state model.

**Affected Modules:**
- `tool/RAGTool/app/agent/langgraph_agent.py` — reimplement or remove
- `tool/RAGTool/` — preserve vector store, BM25, chunking, HyDE, BGE reranker components
- `requirements/` — remove `langgraph-core` dependency

**ADR Impact:** Reinforces ADR-0001/0002 (deterministic pipeline, LLM for assessment only). Removes a contradiction in the dependency graph.

**Recommended Benchmark:** RAG retrieval quality (must maintain or improve). RAG retrieval latency (must not increase by >20%). Dependency count reduction.

---

### Item 11: SQLite as Default Persistence (Replace JSON Files)

**Problem Statement:**
Orion currently has two persistence backends: JSON files (default, zero-config) and PostgreSQL (optional, multi-instance). JSON files lack:
- Concurrency safety (no WAL, no locking beyond `threading.RLock`).
- Query capability (no search across sessions, no filtering by date/status).
- Migration support (schema changes require manual JSON transformation).

FAR recommended REJECT (adding SQLite as third backend). AC correctly reframed: **replace** JSON files with SQLite, reducing backends from 2 to 1 for single-user deployments while keeping PostgreSQL for multi-instance. This decreases maintenance, not increases it.

**Expected Benefit:**
- Concurrency safety (SQLite WAL mode).
- FTS5 full-text search across sessions.
- Schema migrations via Alembic (consistent with PostgreSQL path).
- Reduces persistence backends from 2 to 1 for single-user deployments (SQLite replaces JSON).
- Zero-config — SQLite requires no external daemon.

**Implementation Complexity:** Medium (300-400 LOC).
- `SQLiteConversationStore` implementing the same interface as `PostgresConversationStore`.
- FTS5 virtual table for session search.
- WAL mode for concurrent read/write.
- Alembic migrations (shared with PostgreSQL where possible).
- Migration path from JSON files to SQLite (one-time import).
- Removal of JSON file storage code after migration.

**Architectural Risk:** Low. SQLite replaces JSON as default. PostgreSQL remains for multi-instance. Migration path for existing JSON sessions.

**Maintenance Cost:** Net reduction. 2 backends → 1 for single-user, PostgreSQL for multi-instance. Shared migration infrastructure between SQLite and PostgreSQL.

**Dependencies:** Item #3 (Unified Configuration Accessor) — storage backend selection through unified config.

**Affected Modules:**
- New: `src/backend/sqlite_store.py` — `SQLiteConversationStore`
- `src/agent/conversation_store.py` — interface refinement for backend-agnostic API
- `src/backend/db.py` — shared migration infrastructure
- `config/servers.json` — storage backend selection

**ADR Impact:** Consistent with ADR-0004 (dedicated storage mechanism for state). Does NOT introduce checkpoint-based state management.

**Recommended Benchmark:** Session write/read latency (must not increase by >10% vs. JSON). Concurrent access safety test. JSON-to-SQLite migration success rate.

---

### Item 12: Configuration Error Handling Policy

**Problem Statement:**
Orion's configuration error handling is inconsistent across sources (verified by AC):
1. `_load_server_config()` raises `RuntimeError` if `servers.json` is missing.
2. `_load_tools_config()` silently returns `{}` if `tools.json` is missing.
3. `_build_assessment_adapter()` casts config values with `int()` and `float()` — non-numeric values crash.
4. Some env vars have defaults, others don't — no documented policy.

This inconsistency means the same class of error (missing/invalid config) produces three different behaviors: crash, silent default, or wrong behavior. Item #2 (Pydantic validation) catches schema errors, but a consistent policy is needed for what happens when validation fails and how errors are reported.

**Expected Benefit:**
- Consistent error behavior across all configuration sources.
- Actionable error messages (which file, which key, what was expected, what was received).
- Documented policy for configuration error handling (crash early, loud, and with context).

**Implementation Complexity:** Low (50-100 LOC).
- `ConfigurationError` exception hierarchy.
- Consistent error formatting (file path, key path, expected type, received value).
- Startup validation with all errors collected before exit (not fail-on-first).
- Documented policy added to project docs.

**Architectural Risk:** Very Low. Changes error handling from inconsistent to consistent.

**Maintenance Cost:** Low. Single error handling path.

**Dependencies:** Item #2 (Pydantic validation) and Item #3 (Unified Config Accessor). The error handling policy is applied through the accessor.

**Affected Modules:**
- New: `src/shared/config_errors.py` — `ConfigurationError`, error formatter
- `src/shared/config.py` — apply consistent error handling
- `src/agent/runtime_factory.py` — replace ad-hoc error handling
- `docs/` — document configuration error handling policy

**ADR Impact:** None. Operational policy, not architectural.

**Recommended Benchmark:** Error message clarity test — invalid config must produce actionable error within 3 lines of output.

---

### Item 13: Plugin/Extension System [HORIZON]

**Problem Statement:**
Orion has no plugin system for community-contributed monitoring platform integrations (Datadog, Prometheus, AWS CloudWatch, New Relic). Adding a new monitoring platform requires code changes in `runtime_factory.py`.

**Why This Is Horizon, Not Backlog:**
- FAR correctly classified this as ROADMAP — Orion is a vertical tool with a bounded domain. The comparison projects need plugins because no single team can anticipate every coding task, research query, or messaging platform. Infrastructure monitoring has a finite set of data sources.
- High implementation cost (800-1200 LOC) with uncertain ecosystem return.
- Must enforce `Capability` metadata contract on plugins — non-trivial constraint for plugin authors.
- Security implications: plugins introduce untrusted code, requiring Item #4 (Security Pipeline) as prerequisite.
- Item #5 (Tool Auto-Discovery) achieves 80% of the plugin value (reducing registration from 4 steps to 1) at 20% of the cost.

**Gates for Promotion to Backlog:**
1. Community demand emerges for ≥3 specific monitoring platform integrations.
2. Item #4 (Security Pipeline) is complete.
3. Item #5 (Tool Auto-Discovery) is complete.
4. A plugin API design that enforces the `Capability` metadata contract exists.
5. A commitment to API stability and backward compatibility is made.

**Implementation Estimate (if promoted):** 800-1200 LOC. `ToolProvider` ABC, `PluginManager` with discovery paths, registration context, lifecycle hooks.

---

## 3. Sprint Grouping

### 3.1 Grouping Principles

1. **Each sprint delivers independently verifiable value.** No sprint is purely preparatory.
2. **Dependencies flow forward.** Sprint N items depend only on Sprint 1..N items (or no dependencies).
3. **Risk is front-loaded.** The highest-risk architectural items (ADR divergence, config fragility) are addressed first.
4. **Cross-module refactoring is minimized.** Each sprint touches a bounded set of modules.
5. **Orion's architecture, ADRs, and design philosophy are preserved.** No item introduces LLM-driven tool selection, checkpoint-based state, or autonomous agent loops.

### 3.2 Sprint 1: Foundation & Safety (Weeks 1-2)

**Goal:** Fix architectural documentation, eliminate configuration fragility, and establish the foundation for all subsequent work.

| # | Item | Priority | Category | Effort | Rationale |
|---|------|----------|----------|--------|-----------|
| 1 | ADR-0001 Reconciliation | P0 | Foundation | ~100 LOC docs | Corrects the largest architectural documentation risk before any implementation work begins. Prevents future contributors from building against wrong ADRs. |
| 2 | Configuration Schema Validation (Pydantic) | P0 | Quick Win | 100-150 LOC | Catches config errors at startup. Every subsequent item builds on validated config. Lowest effort, lowest risk, highest immediate benefit. |
| 12 | Configuration Error Handling Policy | P3 | Foundation | 50-100 LOC | Bundled with Item #2 — consistent error handling is a natural extension of Pydantic validation. |
| 3 | Unified Configuration Accessor | P0 | Foundation | 200-300 LOC | Prerequisite for Items #2, #8, #11. Single source of truth for all 11 config sources. |

**Sprint 1 Deliverables:**
- ADR-0001 updated with SUPERSEDED notice and cross-reference to ADR-0002.
- New ADR documenting the deterministic pipeline architecture.
- Pydantic models for all configuration files with startup validation.
- `OrionConfig` unified accessor replacing scattered config reads.
- Consistent error handling across all 11 configuration sources.
- ~500 LOC total.

**Affected Modules (Sprint 1):**
- `docs/adr/` — ADR updates
- `src/shared/config.py` — new
- `src/shared/config_errors.py` — new
- `src/agent/runtime_factory.py` — migrate config reads
- `src/agent/deterministic_agent.py` — migrate env var reads
- `src/backend/app.py` — validate at startup
- `src/cli/main.py` — validate at CLI entry

---

### 3.3 Sprint 2: Core Strengthening (Weeks 3-5)

**Goal:** Add architectural safety guarantees, improve reliability, and simplify the developer experience.

| # | Item | Priority | Category | Effort | Rationale |
|---|------|----------|----------|--------|-----------|
| 4 | Capability-Level Security Pipeline | P1 | Foundation | 200-300 LOC | Architectural enforcement of read-only execution. Must precede Item #5 (auto-discovered tools must pass inspection). Fulfills ADR-0001 safety obligation. |
| 5 | Tool Auto-Discovery / Simplified Registration | P1 | Refactor | 150-250 LOC | Reduces tool registration from 4 steps to 1. Auto-discovered tools route through security pipeline from Item #4. |
| 6 | Retry Policy Unification | P1 | Foundation | 100-150 LOC | Eliminates 6+ distributed retry implementations. Consistent retry behavior across all pipeline stages. |

**Sprint 2 Deliverables:**
- Inspector chain (`ReadOnlyInspector`, `TargetInspector`, `ParameterSafetyInspector`) in `KnowledgeTool._dispatch()`.
- Security guard in `chat()` method.
- `ToolRegistry` with auto-discovery scanning `tool/` subdirectories.
- `RetryPolicy` + `RetryExecutor` integrating into `ExecutionRuntime`.
- ~550 LOC total.

**Affected Modules (Sprint 2):**
- `src/pipeline/security/` — new
- `src/tool/registry.py` — new
- `src/pipeline/retry.py` — new
- `src/tool/knowledge_tool.py` — insert inspector chain
- `src/agent/deterministic_agent.py` — chat guard
- `src/agent/runtime_factory.py` — integrate auto-discovery
- `src/pipeline/execution_runtime.py` — integrate retry
- `src/pipeline/execution_plan.py` — replace distributed retry
- `src/pipeline/execution_graph.py` — replace distributed retry
- `src/pipeline/target_resolver.py` — replace distributed retry

---

### 3.4 Sprint 3: Refinement & Deferred (Weeks 6-8)

**Goal:** Improve maintainability, enable multi-provider deployment, and resolve architectural inconsistencies.

| # | Item | Priority | Category | Effort | Rationale |
|---|------|----------|----------|--------|-----------|
| 7 | Prompt Template Extraction | P2 | Refactor | 150-200 LOC | Separates prompt engineering from code. Enables non-developer prompt iteration. Preserves all existing prompt strengths. |
| 8 | Multi-Provider LLM Support with Failover | P2 | Foundation | 200-400 LOC | Fulfills ADR-0001 model-agnostic goal. Production redundancy. Air-gapped deployment support. Requires Item #7 for per-provider prompt tuning. |
| 9 | Immutable Pipeline State | P2 | Refactor | 200-300 LOC | Eliminates temporal coupling. Enables independent stage testing. Prevents AttributeError crashes from missing fields. |
| 10 | RAG Subsystem Rationalization | P3 | Refactor | 300-500 LOC | Resolves architectural inconsistency (LangGraph dependency contradicts deterministic pipeline philosophy). |
| 11 | SQLite as Default Persistence (Replace JSON) | P3 | Future | 300-400 LOC | Replaces JSON files with SQLite for single-user deployments. Enables FTS5 search. Reduces backends from 2 to 1 for default case. |

**Sprint 3 Deliverables:**
- 11 intent-specific `.j2` prompt templates with Jinja2 rendering.
- Anthropic adapter as second `AssessmentModelAdapter` implementation.
- Provider registry with failover chain and credential pool.
- `PipelineState` immutable dataclass with state update merging.
- RAG subsystem reimplemented using deterministic pipeline patterns.
- `SQLiteConversationStore` replacing JSON file storage.
- ~1,400 LOC total.

**Affected Modules (Sprint 3):**
- `config/prompts/` — new
- `src/model/protocol/prompt_loader.py` — new
- `src/model/providers/` — new
- `src/shared/pipeline_state.py` — new
- `src/backend/sqlite_store.py` — new
- `src/model/protocol/prompt_builder_v2.py` — migrate to templates
- `src/model/llm_client.py` — refactor for multi-provider
- `src/model/llm_assessment_adapter.py` — may need refinement
- `src/pipeline/` — all stages migrated to immutable state
- `src/agent/deterministic_agent.py` — pipeline state migration
- `tool/RAGTool/` — reimplement agent loop
- `src/agent/conversation_store.py` — interface refinement

---

## 4. Implementation Dependency Graph

```
Sprint 1 ─────────────────────────────────────────────────────────────────
│
├── ADR-0001 Reconciliation (no deps) ──────────────────────────────────►
│
├── Config Error Handling (no deps) ──┐
│                                      ├──► Unified Config Accessor ──► all subsequent items
├── Config Schema Validation (no deps)─┘
│
Sprint 2 ─────────────────────────────────────────────────────────────────
│
├── Security Pipeline (depends: Unified Config) ──┐
│                                                  ├──► Tool Auto-Discovery (depends: Security Pipeline)
│                                                  │
├── Retry Policy Unification (depends: Unified Config)
│
Sprint 3 ─────────────────────────────────────────────────────────────────
│
├── Prompt Template Extraction (depends: Unified Config) ──┐
│                                                           ├──► Multi-Provider LLM (depends: Prompt Templates, Unified Config)
│                                                           │
├── Immutable Pipeline State (no hard deps) ───────────────┤
│                                                           │
├── RAG Subsystem Rationalization (depends: Immutable Pipeline State)
│
├── SQLite Persistence (depends: Unified Config)
```

**Key dependency chain:**
`Unified Config → Security Pipeline → Tool Auto-Discovery`
`Unified Config → Prompt Templates → Multi-Provider LLM`

---

## 5. Risk Assessment Matrix

| Item | Architecture Ossification | Performance Regression | Breaking Changes | Migration Complexity |
|------|--------------------------|------------------------|-----------------|---------------------|
| ADR-0001 Reconciliation | None | None | None | None |
| Config Schema Validation | None | None | Valid config → stricter (explicit errors for previously silent failures) | Low |
| Config Error Handling | None | None | Error messages change, behavior for missing config becomes consistent | Low |
| Unified Config Accessor | Low | None | Config access migration (old paths deprecated, not removed) | Medium |
| Security Pipeline | Low | <5ms per tool call | None (additive) | Low |
| Tool Auto-Discovery | Low | <20% registration time | None (additive, old path preserved) | Low |
| Retry Policy Unification | None | <10% for successful calls | Retry behavior becomes consistent (previously varied by module) | Low-Medium |
| Prompt Template Extraction | None | <5% rendering time | None (prompt content unchanged) | Low |
| Multi-Provider LLM | Medium | Per-provider benchmark required | Provider config schema changes | Medium |
| Immutable Pipeline State | Medium | <5% execution time | Stage interface changes (incremental migration) | Medium-High |
| RAG Rationalization | Low | <20% retrieval latency | RAG agent loop replaced | Medium |
| SQLite Persistence | None | <10% vs. JSON | Default storage backend changes, JSON migration path required | Medium |

---

## 6. What Is Excluded and Why

| Item | Source | Reason for Exclusion |
|------|--------|---------------------|
| Streaming Observability | FAR ROADMAP, OIR #4, AC "REMOVE" | Pipeline completes in 1-5 seconds. `run_with_steps()` structured output provides better UX than streaming at this latency. Streaming adds framing overhead without meaningful benefit. Revisit when pipeline execution routinely exceeds 10 seconds. |
| Plugin/Extension System | FAR ROADMAP, OIR #1 (demoted), AC "category error" | Vertical tool with bounded domain. 800-1200 LOC investment with uncertain ecosystem return. Item #5 (Tool Auto-Discovery) achieves 80% of the value at 20% of the cost. Retained as horizon item (#13). |
| Unified Frontend Protocol | FAR ROADMAP, OIR #7 | Strategic investment only needed when adding a fourth frontend. Three existing frontends (CLI, Web, Desktop) are adequately served by current REST API. |
| LLM-Driven Tool Selection | FAR "Never copy" | Violates ADR-0001 and ADR-0002. Deterministic tool selection is Orion's core architectural differentiator. |
| Checkpoint-Based State Management | FAR "Never copy" | Violates ADR-0004. Infrastructure data is stale immediately — checkpoint replay would return wrong results. |
| Docker Sandbox Isolation | FAR "Never copy" | 30-120 seconds cold-start latency unacceptable for CLI tool. Static capability registry provides sufficient safety. |
| MCP-Based Dynamic Tool Loading | FAR "Never copy" | LLM-driven tool selection model conflicts with deterministic pipeline. Introduces non-determinism and security risks without solving a problem Orion has. |

---

## 7. Benchmark Gates

Every item that touches pipeline execution, tool dispatch, LLM interaction, or evidence collection must pass the following gates before merge:

### Gate 1: Intent Classification Regression
**When:** Items #5 (Auto-Discovery), #9 (Pipeline State)
**Metric:** Intent classification accuracy on labeled dataset (~500 requests, Vietnamese + English).
**Threshold:** Must maintain or improve accuracy.

### Gate 2: Evidence Collection Completeness
**When:** Items #5 (Auto-Discovery), #6 (Retry), #9 (Pipeline State)
**Metric:** Evidence completeness score (required evidence collected / total required) on benchmark scenarios.
**Threshold:** Must maintain or improve completeness.

### Gate 3: Assessment Quality
**When:** Items #7 (Prompt Templates), #8 (Multi-Provider LLM)
**Metric:** Assessment quality score (relevance, accuracy, completeness) on labeled assessment dataset (~100 scenarios).
**Threshold:** Must maintain or improve score. New LLM provider must achieve ≥90% of baseline.

### Gate 4: Performance Regression
**When:** Items #4 (Security), #6 (Retry), #8 (Multi-Provider), #9 (Pipeline State), #11 (SQLite)
**Metric:** Pipeline execution time (excluding LLM assessment), tool call count, parallel ratio.
**Threshold:** Execution time must not increase by >10%. Tool call count must not increase. Parallel ratio must not decrease.

### Gate 5: Security Coverage
**When:** Item #4 (Security Pipeline)
**Metric:** Percentage of tool execution paths passing through inspector chain.
**Threshold:** 100% coverage (pipeline path + chat path).

---

## 8. Summary

| Metric | Count |
|--------|-------|
| Total items in backlog | 13 |
| Sprint 1 items (Weeks 1-2) | 4 |
| Sprint 2 items (Weeks 3-5) | 3 |
| Sprint 3 items (Weeks 6-8) | 5 |
| Horizon items | 1 |
| Items excluded | 7 |
| Total estimated LOC | ~2,550 |
| Quick Wins | 1 (Config Schema Validation) |
| Foundation items | 6 (ADR Reconciliation, Config Accessor, Config Errors, Security, Retry, Multi-Provider) |
| Refactor items | 4 (Auto-Discovery, Prompts, Pipeline State, RAG) |
| Future items | 2 (SQLite, Plugin System) |

**Implementation order rationale:** Foundation and safety first (Sprint 1: ADRs, configuration), then core architectural improvements (Sprint 2: security, tool discovery, retry), then maintainability and advanced features (Sprint 3: prompts, multi-provider, state refactoring, RAG, SQLite). Each sprint delivers independently verifiable value. Dependencies flow forward. No item introduces patterns that contradict Orion's ADR-backed design philosophy.

---

*Document synthesized from FINAL_ARCHITECTURE_REVIEW.md, ARCHITECTURE_CRITIQUE.md, and orion_improvements_ranked.md.*
*All quantitative claims verified against Orion source code at `/home/binh/projects/Orion_agent/`.*
*No source code was modified.*
