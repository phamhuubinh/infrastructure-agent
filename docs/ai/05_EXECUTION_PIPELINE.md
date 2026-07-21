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
Capability Resolution  (capability_resolver.py, capability_router.py, capability_library.py)
    │
    ▼
Execution Planning     (execution_planner.py, execution_plan.py)
    │
    ▼
Execution Graph        (execution_graph.py)
    │
    ▼
KnowledgeTool           (knowledge_tool.py — single entry point)
    │
    ▼
Child Tools              (linux_tool.py / grafana_tool.py / zabbix_tool.py / internet_tool.py / knowledge_base_tool.py)
    │
    ▼
Evidence Merge          (evidence_merge.py, evidence_package.py, evidence_completeness.py)
    │
    ▼
┌──────────────────────────────────────────────────┐
│  DeterministicAgent._assess()                     │
│    ├── DeterministicResponder (short-circuit)     │
│    │   → nếu có kết quả, trả về luôn, skip LLM   │
│    └── AssessmentAdapter → AssessmentRequest      │
│        → PromptBuilder → LLM Assessment           │
│        → trả kết quả + tool links                 │
└──────────────────────────────────────────────────┘
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
## Step 4 — Capability Resolution
Resolve the evidence requirements into concrete capabilities. Each evidence name (e.g. "CPU Information") maps to an operational capability via `CapabilityLibrary`. The `CapabilityRouter` builds the route table mapping capabilities to KnowledgeTool (source, resource) pairs. This step also validates that every required capability has a registered route.

## Step 5 — Execution Planning
The evidence plan + resolved capabilities become a concrete execution plan. The `ExecutionPlanner` schedules each capability as an `ExecutionStep` with dependency ordering. This step determines what runs in parallel vs. sequentially.

## Step 6 — Execution Graph
The execution plan is compiled into an `ExecutionGraph` — a DAG of `ExecutionNode` objects with dependency edges. Independent nodes execute in parallel whenever possible. The graph defines execution order, not what to collect (that was Step 3).
## Step 7 — Evidence Collection
Execution graph nodes call `KnowledgeTool`, which dispatches to Child Tools (e.g. `LinuxTool` → Linux target over SSH, `GrafanaTool` → Grafana API, `InternetTool` → HTTP fetch). Each Child Tool returns normalized operational evidence. The pipeline never calls a Child Tool directly — `KnowledgeTool` is the only entry point (see `06_TOOL_AND_CAPABILITY_DESIGN.md`).
## Step 8 — Evidence Merge
Collected evidence is combined into one unified, normalized, deterministic, complete package, ready for assessment. The Assessment Model should receive one complete evidence package whenever practical, rather than being called incrementally.
## Step 9 — Assessment
The Assessment Model interprets collected evidence: explains observations, identifies relationships, evaluates operational impact, produces recommendations. It never performs investigation itself — it only reads what was already collected.
## Deterministic Responder (short-circuit, outside pipeline)
The `DeterministicResponder` (`src/pipeline/deterministic_responder.py`) is not a pipeline stage — it runs in `DeterministicAgent._assess()` (`src/agent/deterministic_agent.py`) after evidence has been merged. Before calling the LLM, the agent checks whether the collected evidence is simple enough to answer without the model (e.g. "Is SSH service running?" — the service status output directly answers the question). If matched, the response is produced deterministically and the assessment step is skipped entirely. This reduces token usage and latency for trivial queries.

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
