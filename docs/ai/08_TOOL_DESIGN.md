# 08 - Tool Design
This document defines the design principles for all Child Tools.
It does not describe implementation details.
It defines how tools should behave within the platform.
---
# Purpose
Child Tools are responsible for collecting operational evidence.
Their responsibility is deterministic execution.
They are never responsible for:
- reasoning
- planning
- assessment
- workflow decisions
---
# Tool Responsibilities
Every Child Tool should:
- collect operational evidence
- normalize outputs
- expose capability metadata
- validate parameters
- return deterministic results
Child Tools should never:
- interpret evidence
- make recommendations
- generate conclusions
- communicate with the Assessment Model
---
# Domain Ownership
Each Child Tool owns exactly one infrastructure domain.
Examples
```
LinuxTool
```
```
DockerTool
```
```
VMwareTool
```
```
ZabbixTool
```
```
GrafanaTool
```
```
GraylogTool
```
A Child Tool should never access another infrastructure domain.
---
# Capability Ownership
Every capability belongs to exactly one Child Tool.
Example
```
LinuxTool
↓
running_services
```
Capability implementations must never be duplicated.
---
# Deterministic Execution
Every capability should produce the same result when executed against the same infrastructure state.
Child Tools must avoid hidden state.
Outputs should depend only on:
- input parameters
- infrastructure state
---
# Operational Evidence
Child Tools should return operational evidence rather than raw infrastructure output.
Preferred
```
Running
Enabled
PID
Port
Version
```
Avoid returning large raw command outputs unless explicitly requested.
---
# Normalization
Tool outputs should use consistent structures.
Examples
```
status
version
hostname
filesystem
package
```
Avoid exposing infrastructure-specific formatting when a normalized representation is possible.
---
# Composite Capabilities
Whenever practical, Child Tools should expose operational capabilities instead of low-level wrappers.
Prefer
```
assess_machine()
```
instead of
```
cpu()
memory()
disk()
filesystem()
network()
```
Composite capabilities reduce:
- execution overhead
- model interaction
- token usage
---
# Atomic Capabilities
Atomic capabilities should remain reusable.
Examples
```
running_services
```
```
installed_packages
```
```
filesystem_usage
```
Composite capabilities should reuse atomic capabilities rather than duplicate logic.
---
# Parameter Validation
Tools should validate parameters before execution.
Examples
- missing target
- unsupported capability
- invalid arguments
Validation failures should produce structured errors.
---
# Error Handling
Errors should be deterministic.
Preferred behaviour
- explain failure
- identify failed capability
- preserve successful evidence
- continue execution whenever possible
One capability failure should not terminate an entire investigation unless the failure prevents meaningful assessment.
---
# Capability Metadata
Every capability should expose metadata.
Recommended fields
- name
- description
- supported targets
- parameters
- produced evidence
- estimated execution cost
- execution characteristics
Metadata should describe behaviour rather than implementation.
---
# Performance
Child Tools should minimize unnecessary work.
Prefer
- batching
- caching within a single execution
- parallel execution
- lightweight queries
Avoid duplicate infrastructure access.
---
# Parallel Execution
Independent capabilities should execute concurrently whenever practical.
Example
```
CPU
Memory
Filesystem
↓
Parallel
```
Avoid sequential execution without dependency.
---
# Source of Truth
Child Tools should always prefer live infrastructure.
Examples
```
Linux
```
```
Docker Engine
```
```
VMware API
```
```
Zabbix API
```
Cached information should never replace live evidence.
---
# Provider Usage
Providers are optional.
Use a Provider only when infrastructure access becomes sufficiently complex.
Simple infrastructure access may remain inside the Child Tool.
---
# Stateless Design
Child Tools must remain stateless.
They should never retain:
- execution history
- previous observations
- previous responses
- investigation state
Each execution must be independent.
---
# Benchmarkability
Every capability should be benchmarkable.
Capability quality should be measurable through:
- correctness
- completeness
- execution time
- evidence quality
- failure behaviour
Capabilities should evolve through benchmark improvements rather than feature expansion.
---
# Evolution
New capabilities should exist only when:
- benchmark scenarios require additional evidence
- existing capabilities cannot answer an operational question
- reuse is expected
Avoid speculative capability design.
---
# Design Principles
Every Child Tool should be:
- deterministic
- reusable
- composable
- stateless
- benchmarkable
- implementation independent
- token efficient
---
# Final Principle
A Child Tool exists to collect evidence.
It should never attempt to explain that evidence.
Evidence collection belongs to Child Tools.
Evidence interpretation belongs to the Assessment Model.
