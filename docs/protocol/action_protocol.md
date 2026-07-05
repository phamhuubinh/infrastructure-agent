# Action Protocol
## Purpose
The Action Protocol defines how the Reasoning Model communicates with the Agent.
The protocol follows a single Action → Observation loop.
The Reasoning Model generates exactly one Action at a time and decides whether another Action is required after receiving an Observation.
---
# Communication Flow
```
User
    │
      ▼
Reasoning Model
    │
      ▼
Action
    │
      ▼
Agent
    │
      ▼
Runtime
    │
      ▼
Tool
    │
      ▼
Observation
    │
      ▼
Agent
    │
      ▼
Reasoning Model
    │
    ├── Next Action
    └── Final Response
```
---
# Responsibilities
## Reasoning Model
Responsible for:
- Understanding the user's request.
- Generating one Action.
- Analyzing Observations.
- Deciding whether to continue or finish.
Never:
- Execute Actions.
- Access external systems directly.
- Collect data.
---
## Agent
Responsible for:
- Receiving an Action.
- Validating the Action.
- Dispatching the Action to Runtime.
- Returning the Observation.
Never:
- Perform reasoning.
- Modify the Action.
- Modify the Observation.
- Decide the next Action.
---
## Runtime
Responsible for:
- Executing the Action.
- Invoking the appropriate Tool.
- Collecting the Observation.
- Returning execution results.
Never:
- Perform reasoning.
- Decide workflow.
- Modify business logic.
---
## Tool
Responsible for:
- Performing one atomic operation.
- Accessing external systems.
- Returning one Observation.
Never:
- Perform reasoning.
- Call other Tools.
- Decide the next Action.
---
# Rules
- One response from the Reasoning Model contains exactly one Action.
- One Action targets exactly one Tool.
- One Tool execution returns exactly one Observation.
- Every Observation is returned to the Reasoning Model before another Action is generated.
- The session ends only when the Reasoning Model returns a Final Response.
---
# Constraints
- Stateless.
- No pre-generated execution plan.
- No workflow engine.
- No business logic in Agent, Runtime or Tool.
- No component may infer missing information.
---
# Design Principles
- One Action at a time.
- One responsibility per component.
- Explicit communication.
- Low coupling.
- Model-driven reasoning.
- Simple before complex.
