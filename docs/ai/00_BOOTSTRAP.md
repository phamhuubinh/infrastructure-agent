# 00 - Bootstrap
> Read this document first.
If multiple documents conflict, follow this priority:
1. Development Rules (02)
2. Architecture (01)
3. Project State (03)
4. Architecture Decisions (04)
This document defines the project's philosophy, design principles, and the responsibilities of each major component.
---
# Project Status
The MVP is complete.
The project has entered the **Platform Evolution** phase.
Future development focuses on improving investigation quality, reducing token usage, and increasing deterministic execution.
All significant changes must be validated through automated tests and benchmarks.
---
# Project Vision
Build an Infrastructure AI Agent that is:
- Evidence-Driven
- Tool-Based
- Deterministic whenever possible
- Stateless
- Token Efficient
- Maintainable
- Extensible
- Benchmark-Driven
- Free from unnecessary complexity
The objective is **not** to build a chatbot.
The objective is to build an **Infrastructure Investigation Engine**.
---
# Core Philosophy
The project follows one fundamental principle:
> **Code investigates. AI explains.**
Whenever deterministic logic can solve a problem, deterministic logic should be preferred over AI reasoning.
The language model should consume evidence, not generate investigation workflows.
---
# Responsibilities
## Language Model
The language model performs reasoning on collected evidence.
Responsibilities:
- Understand the user's request.
- Interpret collected evidence.
- Compare observations.
- Explain findings.
- Produce assessments.
- Provide recommendations.
The language model should not:
- Plan investigation workflows.
- Decide execution strategies.
- Discover capabilities.
- Perform infrastructure access.
- Execute commands.
- Read external systems directly.
---
## Execution Engine
The Execution Engine coordinates every investigation.
Responsibilities:
- Resolve user intent.
- Resolve investigation target.
- Select evidence templates.
- Execute investigation graphs.
- Coordinate tool execution.
- Merge collected evidence.
The Execution Engine contains deterministic logic only.
It never performs AI reasoning.
---
## Tools
Tools collect operational evidence.
Responsibilities:
- Execute commands.
- Query APIs.
- Read inventories.
- Inspect configurations.
- Normalize results.
- Compute deterministic summaries.
Tools never:
- Perform reasoning.
- Make recommendations.
- Decide investigation flow.
- Generate conclusions.
Whenever possible, tools should return operational evidence instead of raw data.
---
## Providers
Providers communicate with the Source of Truth.
Responsibilities:
- Execute infrastructure access.
- Return raw information.
Providers never know:
- User requests.
- AI.
- Investigation workflow.
- Business logic.
---
# Evidence First
Investigation quality depends primarily on evidence quality.
Always prefer:
```
Better Tool
↓
Better Evidence
↓
Better Assessment
```
instead of
```
Larger Prompt
↓
Larger Model
↓
More Reasoning
```
The preferred solution is improving deterministic evidence, not increasing prompt complexity.
---
# Deterministic First
Whenever a problem can be solved without AI, it should be solved without AI.
Examples include:
- Intent routing
- Target resolution
- Capability selection
- Evidence planning
- Parallel execution
- Result aggregation
- Severity calculation
- Threshold evaluation
AI should only be used when deterministic logic is insufficient.
---
# Stateless Execution
Every investigation is independent.
Execution state exists only during a single request.
After completion:
- execution state is discarded
- observations are discarded
- tool outputs are discarded
- runtime context is discarded
Only lightweight summarized session knowledge may remain.
---
# Session Memory
Session Memory stores summaries only.
It never stores:
- raw observations
- command output
- API responses
- reasoning history
- conversation history
Session Memory exists only to reduce unnecessary evidence collection.
It never replaces the Source of Truth.
---
# Source of Truth
Infrastructure is always authoritative.
Examples:
- Operating Systems
- Hypervisors
- Monitoring Platforms
- Network Devices
- Cloud Platforms
- Configuration Files
Cached information is optional.
Operational decisions should always prefer live evidence.
---
# AI Operating Mode
The user owns the architecture.
By default, AI always operates in **Implementation Mode**.
Implementation Mode means:
- understand the repository
- respect the approved architecture
- implement only the requested scope
- preserve existing behavior unless requested otherwise
- produce the smallest reasonable patch
- validate affected tests
- validate affected benchmarks
- stop after completing the sprint
AI must never:
- redesign architecture
- introduce unnecessary abstractions
- expand implementation scope
- add dependencies without approval
- refactor unrelated code
Architecture Discussion Mode is entered only when explicitly requested.
---
# Development Philosophy
Development should always prioritize:
1. Deterministic execution
2. Evidence quality
3. Tool quality
4. Execution efficiency
5. Assessment quality
6. Benchmark quality
7. AI optimization
Never optimize AI before deterministic execution has been fully utilized.
---
# Sprint Workflow
Each sprint should complete exactly one logical improvement.
Workflow:
1. Understand the repository.
2. Confirm the approved design.
3. Define implementation scope.
4. Present implementation plan.
5. Wait for approval.
6. Implement.
7. Run affected tests.
8. Run affected benchmarks when behavior changes.
9. Fix regressions.
10. Commit.
11. Stop.
One sprint.
One logical change.
One commit.
---
# Final Vision
Build an Infrastructure Agent where:
- Code performs investigation.
- Tools collect evidence.
- AI performs assessment.
- Benchmarks measure quality.
- Infrastructure remains the Source of Truth.
The system should become more accurate by improving deterministic execution rather than relying on larger language models.
---
After reading this document, continue in order:
1. 01 - Architecture
2. 02 - Development Rules
3. 03 - Project State
4. 04 - Architecture Decisions
Only then begin repository analysis.
