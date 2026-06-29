# Runtime Component Specification
# Component: ResultCollector
---
# Purpose
ResultCollector collects the outcome of a single execution.
It gathers execution output, execution errors, and runtime metadata, then assembles them into a consistent `ExecutionResult`.
ResultCollector never executes work or modifies execution lifecycle state.
---
# Responsibilities
ResultCollector is responsible for:
* collecting execution output;
* collecting execution errors;
* collecting runtime metadata;
* assembling `ExecutionResult`;
* ensuring execution result consistency.
ResultCollector must not:
* execute Tools;
* manage lifecycle transitions;
* schedule work;
* dispatch execution results;
* perform retries;
* perform planning;
* perform reasoning.
---
# Ownership
ResultCollector owns:
* execution output aggregation;
* execution error aggregation;
* execution result assembly.
ResultCollector does not own:
* execution lifecycle;
* execution environment;
* execution context;
* execution session;
* execution scheduling.
---
# Dependencies
ResultCollector depends only on the shared models required for result assembly.
Required models include:
* ExecutionResult
* RuntimeMetadata
ResultCollector must never depend on:
* Planner
* Knowledge Model
* Capability
* Tool
* Verification
---
# Inputs
ResultCollector receives:
* execution reference;
* execution output;
* execution error;
* runtime metadata.
---
# Outputs
ResultCollector provides:
* immutable `ExecutionResult`.
---
# State
ResultCollector maintains only temporary aggregation state required to assemble one execution result.
All mutable aggregation state shall be released after result assembly.
---
# Constraints
ResultCollector shall:
* produce exactly one execution result per execution;
* preserve `ExecutionResult` immutability;
* perform deterministic result assembly;
* perform no lifecycle management;
* perform no business logic;
* perform no planning.
---
# Relationships
## LifecycleManager
LifecycleManager determines when an execution reaches a terminal state.
---
## ExecutionEnvironment
ExecutionEnvironment provides runtime metadata.
---
## ResultDispatcher
ResultDispatcher delivers the assembled `ExecutionResult`.
ResultCollector never performs result dispatch.
---
# Failure Handling
ResultCollector is responsible only for failures occurring during result assembly.
Execution output and execution errors shall never be silently discarded.
