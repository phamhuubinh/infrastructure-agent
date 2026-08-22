# ADR-0007 — Deterministic request and investigation pipeline

## Status

Accepted; amended after the Agent v2 controller cutover.

The investigation pipeline remains deterministic after a validated Agent v2
action reaches execution. The superseded part of the original record is the
requirement that lexical code classify every request before any model call.

## Context

Infrastructure investigation needs repeatable safety, capability binding,
collection, evidence-validity, recovery, and budget rules. At the same time,
natural-language routing proved too brittle when deterministic regex/keyword
classification was the primary semantic interpreter.

## Decision

For configured RuntimeFactory-built agents, Orion uses the bounded Agent v2
controller/harness boundary:

1. Narrow deterministic controls such as hard-safety/session operations may
   terminate locally; otherwise `ControllerAdapter` returns one bounded
   decision from the user request plus bounded validated context.
2. `DISCOVER` reveals one requested approved category. For an `ACTION`, the
   selected capability detail/schema is disclosed only as required, and
   `AgentActionValidator` enforces read-only intent, target/source authority,
   availability, typed parameters, budgets, and other hard invariants.
3. Invalid, malformed, or unavailable controller decisions/actions fail closed
   and return bounded control feedback or a terminal response rather than
   falling through to lexical routing. `AgentActionExecutor` dispatches only a
   validated action.
4. Deterministic compute uses the first-class calculator action. Current/
   external information is forced through the fixed Internet verification path.
5. Linux/Grafana/Zabbix inspection reaches `KnowledgeTool` and the existing
   reviewed execution implementation.
6. The approved action enters reviewed runtime implementation: host actions
   dispatch through `KnowledgeTool`, Internet through the external verifier,
   and calculator through its deterministic first-class boundary.
7. For an ordinary v2 tool action, `AgentActionExecutor` packages its
   `ToolResult` into an `EvidencePackage`; Internet returns verified action
   evidence and calculator returns a `CalculatorContractResult`.
   `AgentObservationSerializer` converts that typed result into a compact,
   bounded controller observation. This bridge does not automatically run the
   full legacy completeness, Findings, or health-reasoning pipeline.
8. The controller may produce a final candidate. `CompletionCheck` evaluates
   hard v2 invariants over constraints and observations; rejection becomes
   compact control feedback for another bounded round. Acceptance reaches the
   existing artifact/config, sanitizer, response-budget, and public-trace
   boundaries before the single user-visible response.
9. The bounded controller loop continues through compact observations until a
   deterministic completion/final boundary accepts one response or a limit
   stops the request.

Unsafe parameters, unsupported actions, unknown targets, invalid source
constraints, controller failure, and unavailable required evidence return bounded
clarification/refusal/failure outcomes. No failure grants the model a direct
tool API or revives regex-first primary routing.

The existing deterministic investigation pipeline still uses its reviewed
Facts, completeness, reconciliation, Findings, health, recovery, and expansion
components where that pipeline is explicitly selected. This ADR preserves that
historical/current deterministic infrastructure context; it does not make those
stages implicit in every configured Agent v2 action.

## Consequences

- Natural-language reasoning and next approved action selection are model-driven,
  while tool/command authorization remains deterministic.
- The model sees bounded semantic/evidence contracts rather than an unrestricted
  tool registry or execution API.
- Action validation, deterministic recovery, evidence expansion, and stop
  conditions remain reproducible code paths.
- Controller/model failure can prevent a request from running, but cannot
  widen execution authority.
- Insufficient evidence stays explicit and cannot trigger an unbounded
  model-controlled tool loop.

## Related records

- `ADR-0001-agent-responsibility-boundary.md`
- `ADR-0002-llm-assessment-only.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0004-stateless-state-management.md`
- `ADR-0008-evidence-validity.md`
- `ADR-0010-deterministic-external-verification.md`
- `docs/ai/05_EXECUTION_PIPELINE.md`
