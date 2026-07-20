# ADR-0003
# Status
Accepted
---
# Context
The investigation pipeline collects evidence from multiple infrastructure domains: Linux hosts, Grafana dashboards, Zabbix monitoring, and (in the future) Docker, VMware, network devices, and others. Without an explicit architectural rule, each pipeline component could import child tools directly, creating tight coupling between execution orchestration and domain-specific implementations.

Before this ADR was applied, the CapabilityRouter and ExecutionRuntime had knowledge of individual tool classes (e.g., they referenced LinuxTool, GrafanaTool, ZabbixTool directly). This created several problems:

- Adding a new infrastructure domain required touchpoints in the router, the runtime, and the engine — not just the tool itself.
- The assessment layer could accidentally depend on domain-specific tool metadata, breaking the layering rule (AD-012).
- Route resolution logic was scattered across the pipeline, making it hard to reason about where capabilities come from.
- Testing required mocking multiple tool implementations even for tests that only cared about routing.

The pipeline needed a single, stable, tool-agnostic entry point that:
- decouples execution orchestration from infrastructure-specific implementations;
- exposes capability metadata uniformly regardless of the underlying domain;
- allows new Child Tools to be added without changing pipeline code;
- keeps the assessment layer completely isolated from domain implementations.

---

# Decision
`KnowledgeTool` is the single runtime entry point for all evidence collection.

The architecture enforces these rules:

1. **KnowledgeTool is the only bridge between the pipeline and child tools.** No pipeline component (ExecutionEngine, ExecutionRuntime, CapabilityRouter) imports or references any Child Tool (LinuxTool, GrafanaTool, ZabbixTool, etc.) directly. All evidence collection goes through `knowledge_tool.execute({"source": ..., "resource": ...})`.

2. **KnowledgeTool has zero infrastructure knowledge.** It does not run commands, access APIs, or know about specific tool implementations. It is a pure router: given `source` and `resource`, it delegates to the appropriate Child Tool via the TargetRegistry.

3. **Capability metadata flows through KnowledgeTool.** The `CapabilityRouter.build_routes()` method calls `knowledge_tool.get_capability_metadata()` to discover all available capabilities. The router never scans tool modules directly — it relies entirely on KnowledgeTool's aggregated view.

4. **Child Tools are registered externally, not imported.** Registration happens in `runtime_factory.py` via `TargetRegistry`. KnowledgeTool receives a fully-configured registry at construction time. Adding a new domain requires: (a) create a Child Tool class, (b) register it in tools.json and the TargetRegistry, (c) no changes to KnowledgeTool.

5. **The assessment layer never touches tools.** `AssessmentAdapter` receives only an `AssessmentRequest` containing collected evidence. It has no access to KnowledgeTool, the TargetRegistry, or any Child Tool. This enforces AD-002 (LLM assessment only) and AD-012 (one-directional dependencies).

6. **Route resolution is idempotent and deterministic.** `CapabilityRouter` builds its route table once at construction time from KnowledgeTool metadata. Routes are computed as `{operational_name: (source, resource)}`. No runtime discovery, no mutation during execution.

---

# Consequences

## Positive
- Adding a new infrastructure domain requires no changes to pipeline components — just a new Child Tool and a registry entry.
- The assessment layer is completely isolated from domain-specific implementations.
- Route resolution is centralized in CapabilityRouter, which depends only on the KnowledgeTool interface.
- Testing routing logic no longer requires mocking infrastructure tools — a mock KnowledgeTool suffices.
- The architecture enforces the layered dependency rule (AD-012): pipeline code never directly imports tool implementations.

## Negative
- KnowledgeTool becomes a single point of failure in the dispatch path — if it fails, no evidence can be collected.
- The routing layer adds one indirection hop between the runtime and the actual tool execution.
- KnowledgeTool must maintain a complete view of all registered tools and their capabilities, which adds complexity to metadata aggregation.

## Mitigations
- KnowledgeTool is a thin routing layer with no I/O, no state mutation, and no infrastructure access — its failure modes are limited to misconfiguration (missing target, missing source parameter).
- The indirection cost is negligible: route resolution is a dictionary lookup, and the execute() method performs only validation and delegation before calling the Child Tool.
- Metadata aggregation is tested through KnowledgeTool's own test suite and validated at startup (CapabilityLibrary self-validation catches missing operational names at import time).

---

# Referenced files
- `src/tool/knowledge_tool.py` — the single dispatch entry point (168 lines)
- `src/tool/target_registry.py` — registry for targets and child tools
- `src/pipeline/capability_router.py` — builds route table from KnowledgeTool metadata
- `src/pipeline/execution_engine.py` — ExecutionEngine (receives KnowledgeTool at construction)
- `src/pipeline/execution_runtime.py` — Executes through KnowledgeTool dispatch
- `src/agent/runtime_factory.py` — wires KnowledgeTool with TargetRegistry and dependencies
- `src/pipeline/capability_library.py` — single source of truth for operational capability names
- `src/shared/capability.py` — Capability dataclass used by child tool declarations
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` — short-form AD-003 summary of this decision
- `docs/adr/ADR-0002-llm-assessment-only.md` — related ADR (LLM assessment only)
