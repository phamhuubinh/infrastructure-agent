# 04 - Architecture Decisions
This document records long-term architectural decisions.
Each decision contains:
- Decision
- Context
- Reason
- Consequence
Do not include:
- implementation details
- TODOs
- roadmap
- sprint planning
---
# AD-001
## Decision
Infrastructure investigation is deterministic.
## Context
Most infrastructure investigation follows repeatable operational procedures.
## Reason
Deterministic execution is faster, cheaper, easier to benchmark, and more reliable than AI planning.
## Consequence
The platform performs:
- intent resolution
- target resolution
- evidence planning
- capability selection
- execution scheduling
using deterministic code whenever possible.
---
# AD-002
## Decision
The language model performs assessment only.
## Context
The language model is best suited for interpreting evidence rather than controlling execution.
## Reason
Separating investigation from assessment reduces token usage and improves consistency.
## Consequence
The language model:
- interprets evidence
- explains findings
- generates recommendations
It never:
- plans investigations
- executes tools
- accesses infrastructure
---
# AD-003
## Decision
KnowledgeTool is the single runtime entry point for evidence collection.
## Context
The platform supports multiple infrastructure domains.
## Reason
The assessment layer should never depend on domain-specific implementations.
## Consequence
KnowledgeTool:
- exposes capability metadata
- routes requests
- aggregates results
Child Tools remain hidden behind KnowledgeTool.
---
# AD-004
## Decision
Each Child Tool owns exactly one infrastructure domain.
## Context
Operational evidence should remain modular.
## Reason
High cohesion produces simpler maintenance and easier extension.
## Consequence
Examples:
- LinuxTool
- ZabbixTool
- VMwareTool
- DockerTool
Each tool owns only its own domain.
---
# AD-005
## Decision
Capability definitions belong exclusively to Child Tools.
## Context
Capability metadata must remain synchronized.
## Reason
Capability definitions should exist in exactly one location.
## Consequence
- Child Tools define capabilities.
- KnowledgeTool aggregates metadata.
- Execution Engine consumes aggregated metadata.
Capability definitions must never be duplicated.
---
# AD-006
## Decision
Infrastructure is always the Source of Truth.
## Context
Infrastructure changes continuously.
## Reason
Operational decisions must always rely on live evidence.
## Consequence
Runtime always prefers live infrastructure.
Snapshots are optional.
Caches never replace the Source of Truth.
---
# AD-007
## Decision
Execution remains stateless.
## Context
Each investigation must be independent.
## Reason
Stateless execution reduces coupling and prevents stale operational decisions.
## Consequence
Execution state is discarded after every completed investigation.
Only summarized session knowledge may remain.
---
# AD-008
## Decision
Session Memory stores summaries only.
## Context
Repeated evidence collection can be expensive.
## Reason
Summaries reduce unnecessary execution without preserving investigation state.
## Consequence
Session Memory never stores:
- raw observations
- tool outputs
- execution state
- reasoning history
---
# AD-009
## Decision
Evidence quality has higher priority than AI reasoning complexity.
## Context
Operational accuracy depends primarily on evidence quality.
## Reason
Improving deterministic evidence provides more reliable improvements than increasing prompt complexity.
## Consequence
Preferred order:
Tool
↓
Evidence
↓
Assessment
Prompt engineering is a secondary optimization.
---
# AD-010
## Decision
Composite capabilities are preferred over atomic capabilities.
## Context
Operational investigations usually require multiple related observations.
## Reason
Composite capabilities reduce iterations, prompt size, and planning complexity.
## Consequence
Whenever practical, Child Tools should expose operational capabilities rather than low-level API wrappers.
---
# AD-011
## Decision
Execution should minimize model interaction.
## Context
Language model calls are expensive.
## Reason
Reducing reasoning iterations lowers latency and token consumption.
## Consequence
Execution should favor:
- batching
- parallel execution
- deterministic aggregation
before requesting AI assessment.
---
# AD-012
## Decision
Dependencies remain strictly one-directional.
## Context
The platform follows layered architecture.
## Reason
Low coupling simplifies maintenance and evolution.
## Consequence
```
Assessment Model
↓
Execution Engine
↓
KnowledgeTool
↓
Child Tool
↓
Provider
↓
Environment
```
Reverse dependencies are prohibited.
---
# AD-013
## Decision
Providers are optional infrastructure adapters.
## Context
Not every environment requires an additional abstraction layer.
## Reason
Avoid unnecessary abstraction.
## Consequence
Simple environments may be accessed directly by Child Tools.
Providers should exist only when access complexity justifies them.
---
# AD-014
## Decision
Architecture ownership belongs to the human reviewer.
## Context
Architecture evolves more slowly than implementation.
## Reason
Human ownership prevents uncontrolled architectural drift.
## Consequence
AI implements approved architecture.
Architectural changes always require explicit approval.
---
# AD-015
## Decision
Repository state always overrides assumptions.
## Context
Documentation, memory, and reasoning may become outdated.
## Reason
The repository is the authoritative implementation.
## Consequence
Before implementation:
- inspect repository
- understand existing implementation
- reuse existing abstractions
Repository contents always override assumptions.
---
# AD-016
## Decision
Platform evolution is incremental.
## Context
Long-lived infrastructure projects accumulate complexity over time.
## Reason
Small verified improvements are easier to validate and maintain.
## Consequence
Prefer:
- small patches
- benchmark validation
- architecture stability
- deterministic improvements
over large redesigns unless explicitly approved.
