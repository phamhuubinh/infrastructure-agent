# ADR-0001
# Status
Accepted
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
The Agent executes model-generated execution plans.
The Agent never performs reasoning.
The Agent never generates execution plans.
The Agent never modifies execution plans.
The Agent never analyzes execution results.
The reasoning model owns all intelligence.
The Model is the only reasoning component.
---
# Responsibilities
The Agent is responsible for:
* receiving execution plans;
* executing commands;
* collecting execution results;
* preserving execution outputs;
* enforcing execution safety;
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
* business decisions.
---
# Consequences
The architecture becomes model-agnostic.
New reasoning models can replace existing models without modifying the Agent.
The Agent remains deterministic and predictable.
The reasoning model owns all domain knowledge.
The Agent focuses exclusively on execution.
