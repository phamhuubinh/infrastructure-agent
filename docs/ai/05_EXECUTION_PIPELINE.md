# 05 - Execution Pipeline
This document defines the runtime execution flow of the Agent's investigation pipeline. See `02_CURRENT_ARCHITECTURE.md` for how this maps to files today, and `03_PLATFORM_ARCHITECTURE.md` for how it will be invoked once the Agent runs as a platform capability (WP4).
## Purpose
The pipeline transforms a user request into operational evidence, deterministically:
- understand the request
- determine what should be investigated
- collect evidence
- prepare evidence for assessment
## Overview
```
User
    │
    ▼
Intent Resolution      (intent_resolver.py)
    │
    ▼
Target Resolution      (target_resolver.py, target_registry.py)
    │
    ▼
Evidence Planning      (evidence_planner.py, evidence_requirement.py)
    │
    ▼
Execution Graph        (execution_graph.py, execution_planner.py, execution_plan.py)
    │
    ▼
KnowledgeTool           (knowledge_tool.py — single entry point)
    │
    ▼
Child Tools              (linux_tool.py / grafana_tool.py / zabbix_tool.py)
    │
    ▼
Evidence Merge          (evidence_merge.py, evidence_package.py, evidence_completeness.py)
    │
    ▼
Assessment (AI)          (assessment_adapter.py → model/*)
    │
    ▼
Final Response
```
Every stage has exactly one responsibility. Only the Assessment step calls the LLM.
## Step 1 — Intent Resolution
Determine what the user is asking. Examples: Assess Machine, Application Discovery, Security Assessment, Monitoring Assessment, Troubleshooting. Deterministic whenever possible.
## Step 2 — Target Resolution
Determine where the investigation should occur (e.g. `localhost`, `monitor`, `database`, `vm01`, `cluster-a`). If no explicit target is given, deterministic defaults may apply — e.g. "Is there any issue with this machine?" → `localhost`.
## Step 3 — Evidence Planning
Determine **what** evidence is required — not collection itself. Example: `Application Discovery` → Packages, Services, Processes, Listening Ports, Configuration. Example: `Machine Assessment` → CPU, Memory, Disk, Filesystem, Network, Services.
## Step 4 — Execution Graph
The evidence plan becomes an execution graph. Independent nodes execute in parallel whenever possible. The graph defines execution order, not what to collect (that was Step 3).
## Step 5 — Evidence Collection
Execution graph nodes call `KnowledgeTool`, which dispatches to Child Tools (e.g. `LinuxTool` → Linux target over SSH). Each Child Tool returns normalized operational evidence. The pipeline never calls a Child Tool directly — `KnowledgeTool` is the only entry point (see `06_TOOL_AND_CAPABILITY_DESIGN.md`).
## Step 6 — Evidence Merge
Collected evidence is combined into one unified, normalized, deterministic, complete package, ready for assessment. The Assessment Model should receive one complete evidence package whenever practical, rather than being called incrementally.
## Step 7 — Assessment
The Assessment Model interprets collected evidence: explains observations, identifies relationships, evaluates operational impact, produces recommendations. It never performs investigation itself — it only reads what was already collected.
## Composite capabilities
Prefer exposing composite capabilities (`Machine Assessment`) over forcing callers to request individual pieces (`CPU`, `Memory`, `Disk`, `Filesystem` separately). This reduces planning complexity, iterations, and token usage.
## Parallel execution
Independent operations should execute simultaneously (e.g. CPU, Memory, Disk, Network → merge), not sequentially, unless a real dependency requires ordering.
## Early completion
Stop execution once sufficient evidence has been collected for the question asked. Avoid running capabilities whose output will not be used.
## Failure handling
An individual execution failure should not terminate the whole investigation. Preferred behavior: continue collecting remaining evidence, report partial evidence, identify what's missing, and reflect reduced confidence in the assessment rather than failing outright.
## Execution principles
The pipeline should always be: deterministic, stateless, evidence-driven, parallel where practical, benchmarkable, token efficient.
## Final principle
The pipeline exists to collect evidence and should become more deterministic over time. The LLM should receive completed evidence rather than participate in execution.
