# ADR-0004
# Status
Accepted
---
# Context
The Action → Observation architecture executes iteratively.
Execution may span many Action → Observation cycles.
Without explicit architectural rules, Agent, Tool or the Reasoning Model could gradually become implicit state holders.
This creates hidden coupling between iterations.
It also increases prompt size, token usage and the risk of stale execution data.
The architecture therefore requires explicit ownership of workflow state and information lifecycle.
---
# Decision
The entire architecture is stateless by default.
The Reasoning Model does not rely on remembering previous iterations.
The Agent never stores workflow state.
The Runtime never becomes workflow memory.
Tools never become conversation memory.
Workflow state must always be provided explicitly.
The Reasoning Model may only use information available through:
- Prompt
- Bootstrap
- Memory
- Observation
- Tool Result
No component may assume information from previous iterations still exists unless it is explicitly provided again.
---
# Information Classification
Information is divided into two categories.
## Stable Information
Stable Information changes infrequently.
Examples include:
- hardware inventory
- operating system metadata
- SSH configuration
- repository metadata
- capability metadata
Stable Information may be persisted to reduce repeated execution.
Whether previously stored Stable Information should be reused is always determined by the Reasoning Model.
---
## Dynamic Information
Dynamic Information changes during normal system operation.
Examples include:
- CPU usage
- memory usage
- running processes
- service status
- network status
- active connections
- container state
Dynamic Information shall never be assumed to remain valid.
Fresh Dynamic Information must always be collected through an explicit Action.
---
# Ownership
Reasoning belongs exclusively to the Reasoning Model.
Execution belongs to the Agent and Runtime.
Atomic operations belong to Tools.
State persistence belongs only to dedicated storage mechanisms.
No architectural component may implicitly become workflow memory.
---
# Consequences
Execution remains deterministic.
Prompt size is minimized.
Token usage is reduced.
Stale execution data is avoided.
The architecture remains model-driven.
The architecture remains execution-driven.
The architecture remains model-agnostic.
The responsibility of every component remains explicit.
Future storage implementations may evolve independently without changing the responsibilities of the Reasoning Model, Agent, Runtime or Tool.
