# 07 - Capability Graph
This document defines how capabilities are organized and executed.
A Capability Graph maps investigation requirements to evidence collection capabilities.
It is independent of implementation.
It is independent of the Assessment Model.
---
# Purpose
The Capability Graph provides deterministic execution planning.
It answers the following questions:
- Which capabilities are required?
- Which capabilities can run together?
- Which capabilities depend on others?
- When is enough evidence available?
- Which capabilities can be reused?
The Capability Graph never performs investigation.
It only describes execution relationships.
---
# Execution Flow
```
Intent
↓
Evidence Template
↓
Capability Graph
↓
Execution Graph
↓
KnowledgeTool
↓
Child Tool
```
Capability Graph transforms required evidence into executable capabilities.
---
# Capability
A capability is the smallest reusable evidence collection unit.
A capability should answer exactly one operational question.
Examples
```
cpu_information
```
```
memory_information
```
```
installed_packages
```
```
running_services
```
```
process_list
```
Capabilities should be deterministic.
---
# Composite Capability
Composite Capabilities group multiple related capabilities.
Example
```
Machine Assessment
```
↓
```
cpu_information
memory_information
disk_information
filesystem_information
network_information
service_status
```
The Execution Engine may execute the entire composite capability with a single request.
---
# Capability Relationships
Capabilities may have three relationships.
Independent
Dependent
Composite
---
# Independent Capability
Independent capabilities require no other capability.
Example
```
CPU
```
```
Memory
```
```
Filesystem
```
They should execute in parallel whenever possible.
---
# Dependent Capability
Some capabilities require evidence from another capability.
Example
```
Installed Packages
↓
Configuration File
```
Configuration inspection is unnecessary if the application is not installed.
Dependent capabilities execute only after prerequisite evidence exists.
---
# Composite Capability
Composite capabilities represent operational investigations.
Example
```
Application Discovery
```
↓
```
Installed Packages
Running Services
Processes
Listening Ports
```
The composite capability returns a complete evidence package.
---
# Capability Reuse
Capabilities should be reusable across investigations.
Example
```
running_services
```
may be reused by
- Machine Assessment
- Service Assessment
- Application Discovery
- Troubleshooting
Capability logic should never be duplicated.
---
# Execution Strategy
The Execution Engine should prefer
```
Composite
↓
Parallel
↓
Independent
```
Avoid unnecessary sequential execution.
---
# Capability Ownership
Every capability belongs to exactly one Child Tool.
Example
```
LinuxTool
↓
running_services
```
```
ZabbixTool
↓
active_problems
```
Capabilities must never belong to multiple tools.
---
# KnowledgeTool
KnowledgeTool aggregates capability metadata.
KnowledgeTool does not implement capabilities.
Responsibilities
- discover capabilities
- expose metadata
- dispatch requests
- merge results
Capability implementation always belongs to Child Tools.
---
# Capability Metadata
Every capability should expose metadata.
Recommended metadata includes
- name
- description
- required parameters
- optional parameters
- produced evidence
- supported targets
- execution cost
- execution time estimate
Metadata should describe capabilities without exposing implementation details.
---
# Capability Selection
Capability selection should be deterministic.
Selection is based on
- Intent
- Target
- Evidence Template
The Assessment Model should not choose capabilities.
---
# Capability Batching
Compatible capabilities should execute together.
Example
```
CPU
Memory
Filesystem
```
↓
```
LinuxTool
↓
Single execution
```
Batching reduces
- tool calls
- latency
- token usage
---
# Capability Dependencies
Execution order should only exist when required.
Example
```
Package Discovery
↓
Configuration Inspection
```
Avoid artificial dependencies.
Independent capabilities should remain parallel.
---
# Capability Result
Every capability returns normalized evidence.
Capability results should
- be deterministic
- contain operational facts
- avoid presentation formatting
- avoid recommendations
- avoid reasoning
Capabilities produce evidence, not conclusions.
---
# Evolution
New capabilities should only be introduced when
- benchmark scenarios require additional evidence
- existing capabilities cannot satisfy an operational investigation
- reuse is expected
Avoid creating capabilities for isolated implementation needs.
---
# Design Principles
Capability Graphs should always be
- deterministic
- composable
- reusable
- benchmarkable
- parallelizable
- implementation independent
---
# Final Principle
Capabilities represent evidence collection.
The Capability Graph represents investigation logic.
Neither should contain reasoning.
The Assessment Model remains responsible for interpreting collected evidence.
