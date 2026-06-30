# Action Protocol
---
# Purpose
The Action Protocol defines the communication contract between the reasoning model and the Agent.
The protocol is independent of any reasoning model.
The protocol is independent of any execution environment.
---
# Core Principle
The reasoning model owns all reasoning.
The Agent owns all execution.
The Agent never performs reasoning.
The reasoning model never performs execution.
---
# Interaction Model
The protocol follows an iterative Action → Observation loop.
User
↓
Agent
↓
Reasoning Model
↓
Action
↓
Agent
↓
Observation
↓
Reasoning Model
↓
...
↓
Final
↓
Agent
↓
User
---
# Message Types
The reasoning model may produce one of the following messages:
* Action
* Final
The Agent always produces:
* Observation
---
# Termination
The interaction terminates only when the reasoning model produces a Final message.
The Agent never decides when execution should terminate.
---
# Responsibilities
Reasoning Model
* determine the next action;
* evaluate observations;
* decide when enough information has been collected;
* produce the final answer.
Agent
* execute actions;
* collect observations;
* enforce execution safety;
* preserve execution outputs exactly.
---
# Architectural Constraints
Actions shall never contain observations.
Observations shall never contain reasoning.
Final messages shall never contain executable actions.
The Agent shall never modify Action messages.
The Agent shall never modify Observation messages.
The reasoning model shall remain responsible for all reasoning.
