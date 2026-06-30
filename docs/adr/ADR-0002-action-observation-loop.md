# ADR-0002
# Status
Accepted
---
# Context
The original architecture used a complete Execution Plan generated before execution.
Practical experimentation with a reasoning model demonstrated that reasoning naturally occurs as an iterative process.
The reasoning model determines the next action after observing execution results.
---
# Decision
The architecture adopts an Action → Observation loop.
The reasoning model generates exactly one Action at a time.
The Agent executes the Action.
The Agent returns an Observation.
The reasoning model determines whether another Action is required or whether a Final response should be produced.
The reasoning model remains stateless with respect to execution.
The complete interaction history is provided by the Agent at every reasoning step.
---
# Consequences
The reasoning model may dynamically adapt execution.
Execution is no longer limited by a static execution plan.
The Agent remains deterministic.
The reasoning model remains the only reasoning component.
