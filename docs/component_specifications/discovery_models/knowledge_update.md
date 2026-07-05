# Knowledge Update Model Specification
---
# Purpose
KnowledgeUpdate represents structured knowledge produced by the Discovery Engine.
It is the output of one discovery cycle.
KnowledgeUpdate contains structured knowledge updates only.
---
# Responsibilities
KnowledgeUpdate is responsible for:
* representing structured knowledge updates;
* carrying discovery results;
* remaining immutable after creation.
KnowledgeUpdate must never:
* contain planning decisions;
* contain execution state;
* perform reasoning.
---
# Ownership
KnowledgeUpdate is produced by the Discovery Engine.
KnowledgeUpdate is consumed by the Knowledge Model.
---
# Lifecycle
1. Created by the Discovery Engine.
2. Submitted to the Knowledge Model.
3. Consumed according to Knowledge Model policies.
---
# Architectural Constraints
KnowledgeUpdate shall remain:
* immutable;
* deterministic;
* independent of Runtime;
* independent of Planner.
