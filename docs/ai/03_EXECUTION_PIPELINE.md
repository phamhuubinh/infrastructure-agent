# 03 - Execution Pipeline
This document describes how an investigation is executed.
It does not describe implementation details.
It defines the runtime execution flow of the platform.
---
# Purpose
The Execution Pipeline transforms a user request into operational evidence.
Its responsibilities are:
- understand the request
- determine what should be investigated
- collect evidence
- prepare evidence for assessment
The pipeline is deterministic.
---
# Execution Overview
```
User
        │
        ▼
Intent Resolution
        │
        ▼
Target Resolution
        │
        ▼
Evidence Planning
        │
        ▼
Execution Graph
        │
        ▼
KnowledgeTool
        │
        ▼
Child Tools
        │
        ▼
Evidence
        │
        ▼
Assessment Model
        │
        ▼
Final Response
```
Every stage has exactly one responsibility.
---
# Step 1 — Intent Resolution
Determine what the user is asking.
Examples:
```
Assess Machine
```
```
Application Discovery
```
```
Security Assessment
```
```
Monitoring Assessment
```
```
Troubleshooting
```
Intent Resolution should be deterministic whenever possible.
---
# Step 2 — Target Resolution
Determine where the investigation should occur.
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
```
vm01
```
```
cluster-a
```
If no explicit target is provided, deterministic defaults may be applied.
Example:
```
User:
Is there any issue with this machine?
↓
Target:
localhost
```
---
# Step 3 — Evidence Planning
Determine what evidence is required.
Example:
```
Application Discovery
```
↓
```
Packages
Services
Processes
Listening Ports
Configuration
```
Another example:
```
Machine Assessment
```
↓
```
CPU
Memory
Disk
Filesystem
Network
Services
```
Evidence Planning defines **what** should be collected.
It does not perform collection.
---
# Step 4 — Execution Graph
The Evidence Plan becomes an Execution Graph.
Example:
```
Machine Assessment
↓
CPU
Memory
Disk
Network
Services
```
Independent nodes should execute in parallel whenever possible.
The Execution Graph defines execution order.
---
# Step 5 — Evidence Collection
Execution Graph nodes call KnowledgeTool.
KnowledgeTool dispatches requests to Child Tools.
Example:
```
Machine Assessment
↓
KnowledgeTool
↓
LinuxTool
↓
Linux
```
Each Child Tool returns normalized operational evidence.
---
# Step 6 — Evidence Merge
Collected evidence is combined into a unified investigation result.
Merged evidence should be:
- normalized
- deterministic
- complete
- ready for assessment
The Assessment Model should receive one complete evidence package whenever practical.
---
# Step 7 — Assessment
The Assessment Model interprets collected evidence.
Responsibilities include:
- explain observations
- identify relationships
- evaluate operational impact
- produce recommendations
The Assessment Model never performs investigation.
---
# Composite Capabilities
Whenever practical, investigations should expose composite capabilities.
Instead of
```
CPU
Memory
Disk
Filesystem
```
prefer
```
Machine Assessment
```
Composite capabilities reduce:
- planning complexity
- iterations
- token usage
---
# Parallel Execution
Independent operations should execute simultaneously.
Preferred:
```
CPU
Memory
Disk
Network
↓
Merge
```
Avoid sequential execution unless dependencies require it.
---
# Early Completion
Execution should stop when sufficient evidence has been collected.
The platform should avoid unnecessary capability execution.
Example:
```
Question
↓
Evidence Found
↓
Assessment
↓
Stop
```
rather than continuing to collect unrelated information.
---
# Failure Handling
Individual execution failures should not terminate an investigation immediately.
Preferred behavior:
- continue collecting remaining evidence
- report partial evidence
- identify missing information
- explain confidence reduction
The platform should degrade gracefully whenever possible.
---
# Execution Principles
The Execution Pipeline should always be:
- deterministic
- stateless
- evidence-driven
- parallel where practical
- benchmarkable
- token efficient
---
# Final Principle
The Execution Pipeline exists to collect evidence.
It should become increasingly deterministic over time.
The language model should receive completed evidence rather than participating in execution.
