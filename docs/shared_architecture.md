# Shared Architecture
## Definition
The **Shared** layer is the common architectural foundation of the Autonomous Agent.
It defines reusable domain models, contracts, value objects, metadata, requests, responses, and state definitions shared across multiple architectural components.
The Shared layer defines common language only. It never implements behavior.
---
## Purpose
The Shared layer eliminates duplicated model definitions and prevents ownership conflicts between architectural components.
Reusable concepts such as `ExecutionContext`, `ExecutionSession`, `ExecutionResult`, `Plan`, and `ToolResult` exist only once and are shared across the architecture.
The Shared layer is the single source of truth for reusable domain definitions.
---
## Responsibilities
The Shared layer owns reusable definitions including:
* Requests
* Responses
* Results
* Contexts
* Sessions
* States
* Constraints
* Contracts
* Metadata
* Value Objects
* Enumerations
* Identifiers
* Common Error Definitions
These definitions are immutable whenever possible and contain no execution behavior.
---
## Responsibilities Outside the Shared Layer
The Shared layer must never contain:
* Planning
* Execution
* Runtime management
* Tool execution
* Capability resolution
* Verification logic
* Discovery logic
* Knowledge processing
* AI reasoning
* Business logic
* Side effects
* External system interaction
---
## Design Principles
* Single Source of Truth
* Separation of Concerns
* Reusability
* High Cohesion
* Low Coupling
* Immutable Models where possible
* No Business Behavior
* Replaceable Components
---
## Dependency Rules
Every architectural component may depend on the Shared layer.
The Shared layer must never depend on:
* Agent Core
* Planner
* Executor
* Runtime
* Capability
* Tool
* Verification
* Discovery
* Knowledge Model
Dependencies always point toward the Shared layer.
---
## Information Flow
```text
Planner
        ↓
Executor
        ↓
Runtime
        ↓
Shared Models
        ↑
Capability
        ↑
Tool
        ↑
Verification
        ↑
Discovery
        ↑
Knowledge Model
```
Shared provides common models used by all architectural components.
---
## Relationship with Other Components
### Agent Core
Uses Shared definitions for communication between architectural layers.
### Planner
Consumes shared planning models.
### Executor
Consumes shared execution models and produces shared execution results.
### Runtime
Consumes shared execution models.
### Capability
Consumes shared contracts, requests, and results.
### Tool
Consumes shared requests and produces shared results.
### Verification
Consumes shared execution results and produces shared verification results.
### Discovery
Consumes shared observation models and produces shared knowledge artifacts.
### Knowledge Model
Consumes shared domain objects while remaining the owner of persistent knowledge.
---
## Typical Shared Concepts
Examples of reusable concepts include:
* ExecutionContext
* ExecutionSession
* ExecutionState
* ExecutionResult
* ExecutionConstraints
* Plan
* Step
* Goal
* ToolRequest
* ToolResult
* CapabilityRequest
* CapabilityResult
* VerificationResult
* RuntimeMetadata
These examples describe architectural ownership only.
---
## Information Models
The Shared layer defines common information models shared across architectural components.
Examples include:
* Stable Information
* Dynamic Information
* Information Metadata
These models define information structure only.
They never define storage policy, caching behavior, execution policy or ownership decisions.
Architectural components consume these definitions while preserving their own responsibilities.
---
## Architectural Constraints
The Shared layer:
* contains reusable definitions only;
* contains no business behavior;
* contains no execution orchestration;
* contains no planning logic;
* contains no reasoning;
* contains no infrastructure implementation.
---
## Shared Model Specifications
Shared model definitions are maintained under:
* `docs/model_specifications/`
Architecture documents reference the required model specifications.
Implementations must follow the model specifications exactly.
If a required model specification does not exist, implementation must stop until the specification is added.
