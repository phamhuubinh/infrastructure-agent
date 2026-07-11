# 01 - Architecture
## Overview
The platform follows an **Evidence-Driven Architecture**.
Its purpose is to investigate infrastructure deterministically, collect operational evidence, and use a language model only to interpret the collected evidence.
Every component owns exactly one responsibility.
```
                User
                  │
                  ▼
          Intent Resolver
                  │
                  ▼
          Target Resolver
                  │
                  ▼
        Evidence Planner
                  │
                  ▼
        Execution Engine
                  │
                  ▼
          KnowledgeTool
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
 LinuxTool   ZabbixTool   VMwareTool ...
     │            │            │
     ▼            ▼            ▼
 Linux      Zabbix API    vCenter API
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
The investigation pipeline is deterministic.
The language model performs assessment only.
---
# Architectural Layers
The platform consists of seven layers.
1. Intent Resolution
2. Evidence Planning
3. Execution
4. Evidence Collection
5. Source of Truth
6. Assessment
7. Evaluation
Each layer has exactly one responsibility.
---
# 1. Intent Resolution
The first step is understanding what the user wants.
Responsibilities:
- classify user intent
- normalize requests
- identify investigation category
Examples:
- Machine Assessment
- Application Discovery
- Monitoring Assessment
- Security Assessment
- Troubleshooting
Intent Resolution is deterministic.
It should not require AI whenever possible.
---
# 2. Target Resolution
After determining the intent, the platform resolves the investigation target.
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
zabbix
```
Target Resolution determines where evidence should be collected.
It never performs evidence collection itself.
---
# 3. Evidence Planner
Evidence Planner transforms an investigation into an execution plan.
Example:
```
Application Discovery
```
↓
```
Package
Service
Process
Port
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
Evidence Planner is deterministic.
It never performs reasoning.
---
# 4. Execution Engine
Execution Engine coordinates investigation.
Responsibilities:
- execute evidence plans
- schedule capability execution
- batch compatible requests
- execute in parallel whenever possible
- merge evidence
Execution Engine never performs analysis.
It only executes.
---
# 5. KnowledgeTool
KnowledgeTool is the single runtime entry point for evidence collection.
The Assessment Model never communicates directly with child tools.
KnowledgeTool responsibilities:
- expose capability metadata
- route requests
- execute child tools
- aggregate results
- normalize Tool Results
KnowledgeTool never accesses infrastructure directly.
---
# Child Tools
Each Child Tool owns exactly one infrastructure domain.
Examples:
- LinuxTool
- ZabbixTool
- VMwareTool
- DockerTool
- GrafanaTool
- GraylogTool
Each tool:
- collects evidence
- performs deterministic computation
- normalizes outputs
Child Tools never:
- perform reasoning
- decide investigation workflow
- interpret evidence
---
# Composite Capabilities
Child Tools may expose composite capabilities.
Example:
```
assess_machine
```
internally executes:
```
CPU
Memory
Disk
Filesystem
Network
Services
```
Composite capabilities reduce:
- model calls
- iteration count
- prompt size
---
# Providers
Providers are optional.
Providers encapsulate complex access logic.
Examples:
- SSH Provider
- VMware Provider
- Zabbix Provider
- Grafana Provider
Simple environments may be accessed directly by Child Tools.
Providers never know:
- user intent
- AI
- execution workflow
---
# Source of Truth
Infrastructure is always authoritative.
Examples:
- Linux
- Docker
- VMware
- Kubernetes
- Zabbix
- Grafana
- Graylog
Cached information never replaces live infrastructure.
---
# Evidence
Evidence is the primary product of the execution pipeline.
Evidence should be:
- deterministic
- normalized
- composable
- benchmarkable
Whenever possible, tools should return operational evidence instead of raw API responses.
---
# Assessment Model
The language model receives completed evidence only.
Responsibilities:
- interpret evidence
- compare observations
- explain findings
- generate recommendations
The Assessment Model never:
- plans investigations
- executes tools
- discovers capabilities
- accesses infrastructure
---
# Working Context
Working Context exists only during one investigation.
It contains:
- collected evidence
- execution state
- temporary observations
Working Context is discarded after the response is generated.
---
# Dependency Direction
Dependencies are strictly one-way.
```
Assessment Model
        │
        ▼
Execution Engine
        │
        ▼
KnowledgeTool
        │
        ▼
Child Tool
        │
        ▼
Provider (optional)
        │
        ▼
Environment
```
Reverse dependencies are prohibited.
---
# Extending the Platform
Supporting a new infrastructure domain normally requires:
- adding a Child Tool
- optionally adding a Provider
- defining evidence templates
- defining capability metadata
- adding benchmarks
No architectural changes should be necessary.
---
# Architectural Principles
The platform must always preserve:
- Evidence-Driven
- Deterministic Investigation
- Stateless Execution
- Tool-Based Design
- Source of Truth
- Low Coupling
- High Cohesion
- Parallel Execution
- Benchmark-Driven Evolution
- Token Efficiency
- Simplicity
Every architectural decision should reinforce these principles.
