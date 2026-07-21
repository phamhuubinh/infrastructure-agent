# ADR-0001
# Status
Accepted
---
# Cross-reference
Short-form summary: `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-020
---
# Context
Describe the problem.
The project originally explored an autonomous-agent architecture.
During the architectural review, it became clear that reasoning, planning, analysis, and recommendation should belong entirely to the reasoning model.
The Agent should behave like a human operator executing instructions rather than making autonomous decisions.
This ADR establishes the permanent architectural boundary between the Agent and the reasoning model.
---
# Decision
The Agent is an execution engine.
The Agent executes model-generated actions.
The Agent returns raw observations.
The Agent never decides what the next action should be.
The reasoning model decides whether to continue execution or produce the final answer.
The Agent never performs reasoning.
The Agent never generates actions.
The Agent never modifies actions.
The Agent never analyzes execution results.
The reasoning model owns all intelligence.
The Model is the only reasoning component.
---
# Responsibilities
The Agent is responsible for:
* receiving actions;
* executing commands;
* collecting execution results;
* preserving execution outputs;
* enforcing execution safety;
* returning raw observations;
* reporting execution failures.
---
# Non-Responsibilities
The Agent is never responsible for:
* reasoning;
* planning;
* command generation;
* recommendation;
* optimization;
* interpretation;
* knowledge creation;
* deciding the next action;
* business decisions.
---
# Related ADRs
- ADR-0004 (`docs/adr/ADR-0004-stateless-state-management.md`) — stateless execution reinforces the Agent's role as a pure execution engine without workflow memory
- ADR-0002 (`docs/adr/ADR-0002-llm-assessment-only.md`) / AD-002 (`docs/ai/09_ARCHITECTURE_DECISIONS.md`) — LLM assessment only; the Agent's role as execution engine is complementary to keeping the LLM focused on assessment
- AD-012 (`docs/ai/09_ARCHITECTURE_DECISIONS.md`) — one-directional dependencies keep the Agent, tools, and model layers separate
# Consequences
The architecture becomes model-agnostic.
New reasoning models can replace existing models without modifying the Agent.
The Agent remains deterministic and predictable.
The reasoning model owns all domain knowledge.
The Agent focuses exclusively on execution.
Execution becomes an iterative Action → Observation loop rather than a single static execution plan.
