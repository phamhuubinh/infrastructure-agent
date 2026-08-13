# ADR-0003 — KnowledgeTool is the collection entry point

## Status

Accepted.

## Context

The investigation runtime collects evidence from Linux, Grafana, Zabbix, and
public Internet sources. Pipeline orchestration must not depend directly on
domain-specific implementations.

## Decision

`KnowledgeTool` is the only runtime entry point for chat evidence collection.

- `ExecutionRuntime` dispatches `source`, `resource`, and validated parameters
  to `KnowledgeTool`.
- `KnowledgeTool` resolves the registered Child Tool from `TargetRegistry`,
  applies the inspector chain and preflight/metadata checks, then delegates the
  named capability.
- Capability routing is built from metadata aggregated by `KnowledgeTool`.
- Child Tool construction and target registration occur in
  `src/agent/runtime_factory.py`; tool modules are discovered through
  `ToolRegistry`, with explicit compatibility fallbacks for current domains.
- The assessment layer receives evidence contracts and has no reference to
  `KnowledgeTool`, `TargetRegistry`, or Child Tool instances.
- Project RAG uses the separate `/api/rag/*` service path and is not registered
  behind `KnowledgeTool`.

`KnowledgeTool` does not implement Linux commands or Grafana/Zabbix/Internet
API operations. Those strategies stay in their owning Child Tools.

## Consequences

- Dispatch safety and capability validation apply consistently.
- Pipeline execution stays domain-agnostic.
- Capability metadata has one aggregation boundary for planning and routing.
- A `KnowledgeTool` dispatch failure prevents evidence collection but does not
  grant a direct fallback path to a Child Tool.

## Related records

- `ADR-0001-agent-responsibility-boundary.md`
- `ADR-0002-llm-assessment-only.md`
- `ADR-0007-deterministic-pipeline.md`
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-003, AD-005, and AD-011
