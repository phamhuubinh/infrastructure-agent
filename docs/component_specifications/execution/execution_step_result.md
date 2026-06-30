# Execution Step Result Specification
---
# Purpose
Execution Step Result represents the outcome produced by executing a single Execution Step.
Execution Step Result contains execution output only.
Execution Step Result never performs reasoning.
Execution Step Result never modifies execution results.
---
# Responsibilities
Execution Step Result is responsible for:
* representing the outcome of one execution step;
* preserving execution outputs exactly as produced;
* remaining immutable after creation.
Execution Step Result must never:
* analyze execution outputs;
* generate recommendations;
* perform reasoning;
* modify execution outputs.
---
# Ownership
Execution Step Result belongs to the Agent.
Execution Step Result is consumed by the reasoning model.
Execution Step Result is never modified after creation.
---
# Inputs
Execution Step Result is produced by the Agent after executing an Execution Step.
---
# Outputs
Execution Step Result provides execution outputs to the reasoning model.
---
# Lifecycle
The Execution Step Result lifecycle consists of:
1. Created by the Agent.
2. Returned to the reasoning model.
3. Consumed by the reasoning model.
4. Archived or discarded according to higher-level policies.
---
# Architectural Constraints
Execution Step Result shall remain:
* immutable;
* deterministic;
* execution-generated;
* independent of reasoning.
Execution Step Result shall preserve execution outputs exactly as produced.
Execution Step Result shall not contain recommendations.
Execution Step Result shall not contain conclusions.
