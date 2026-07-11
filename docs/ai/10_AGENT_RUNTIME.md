# 10 - Agent Runtime
This document defines the runtime behavior of the Infrastructure Agent.
It describes how investigations are executed.
It does not describe implementation details.
---
# Purpose
The runtime is responsible for executing investigations.
It coordinates execution.
It does not perform reasoning.
It does not interpret evidence.
Its purpose is to transform an investigation request into a complete evidence package.
---
# Runtime Flow
```
User Request
↓
Intent Resolution
↓
Target Resolution
↓
Evidence Template
↓
Capability Graph
↓
Execution Graph
↓
KnowledgeTool
↓
Child Tools
↓
Evidence Merge
↓
Assessment Model
↓
Final Response
```
Every runtime stage has exactly one responsibility.
---
# Runtime Principles
The runtime must always remain:
- deterministic
- stateless
- modular
- benchmarkable
- observable
- token efficient
---
# Session
Each investigation creates exactly one Runtime Session.
A Runtime Session contains:
- execution state
- execution graph
- collected evidence
- execution errors
The Runtime Session exists only for the lifetime of the investigation.
---
# Runtime Context
Runtime Context contains temporary execution information.
Examples:
- execution progress
- completed capabilities
- failed capabilities
- pending capabilities
- merged evidence
Runtime Context is destroyed after the investigation completes.
---
# Intent Resolution
The runtime first determines the investigation objective.
Intent Resolution should be deterministic whenever possible.
Intent Resolution never executes tools.
---
# Target Resolution
The runtime determines where evidence should be collected.
Examples:
```
localhost
```
```
monitor
```
```
database
```
If no explicit target exists, deterministic defaults may be applied.
---
# Evidence Planning
The runtime selects an Evidence Template.
Evidence Planning determines:
- required evidence
- optional evidence
No infrastructure access occurs during this stage.
---
# Capability Resolution
The runtime maps evidence requirements to executable capabilities.
Capabilities should be selected deterministically.
Capability Resolution never performs execution.
---
# Execution Graph
The runtime constructs an Execution Graph.
The graph defines:
- execution order
- dependencies
- parallel opportunities
- completion conditions
The graph should contain the minimum work necessary to complete the investigation.
---
# Execution
The runtime executes the Execution Graph.
Responsibilities include:
- scheduling
- dispatching
- collecting evidence
- monitoring execution
- handling failures
Execution never performs assessment.
---
# Parallel Execution
Independent capabilities should execute concurrently.
Example
```
CPU
Memory
Filesystem
↓
Parallel Execution
```
Avoid sequential execution unless dependencies require it.
---
# Capability Batching
Compatible capabilities should execute together whenever practical.
Example
```
CPU
Memory
Filesystem
↓
LinuxTool
```
instead of three independent tool executions.
Batching reduces:
- latency
- infrastructure access
- token usage
---
# Evidence Merge
Evidence collected from multiple capabilities should be merged into one evidence package.
Merged evidence should be:
- complete
- normalized
- deterministic
The Assessment Model should receive one evidence package whenever practical.
---
# Early Completion
The runtime should stop execution when sufficient evidence has been collected.
Avoid unnecessary capability execution.
Collect only the evidence required to answer the investigation.
---
# Retry Strategy
Retry should occur only for transient failures.
Examples include:
- temporary network failures
- temporary API failures
- timeout
Persistent failures should not be retried indefinitely.
Retry behavior should remain deterministic.
---
# Timeout
Every execution should have a timeout.
A timeout should terminate only the affected capability.
The investigation should continue whenever remaining evidence is sufficient.
---
# Failure Handling
Capability failures should not immediately terminate an investigation.
Preferred behavior:
- continue collecting remaining evidence
- report partial evidence
- identify missing evidence
- reduce confidence if necessary
Graceful degradation is preferred over complete failure.
---
# Runtime Cache
The runtime may cache temporary execution results during a single investigation.
Runtime Cache exists only inside the current Runtime Session.
It must never become persistent storage.
---
# Session Memory
Session Memory is outside the Runtime Session.
It stores only lightweight summaries.
It never stores:
- raw evidence
- command output
- API responses
- execution graphs
---
# Source of Truth
The runtime always prefers live infrastructure.
Cached information must never replace live operational evidence.
---
# Assessment Boundary
The runtime stops after producing a complete evidence package.
Evidence interpretation belongs exclusively to the Assessment Model.
---
# Observability
Every investigation should expose runtime metrics.
Examples include:
- execution duration
- capability count
- failed capabilities
- parallel execution ratio
- evidence completeness
Observability supports benchmarking and debugging.
---
# Runtime Evolution
Runtime improvements should prioritize:
1. Fewer model calls
2. Better batching
3. Better parallel execution
4. Better capability reuse
5. Better evidence quality
New runtime behavior should be benchmark validated before adoption.
---
# Final Principle
The runtime exists to execute investigations.
It should become increasingly deterministic over time.
The language model should remain outside the execution pipeline and receive only completed evidence for assessment.
