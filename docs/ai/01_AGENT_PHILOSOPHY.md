# 01 - Agent Philosophy
This document defines the philosophy behind the Infrastructure Agent.
It does not describe implementation details.
It defines **how the platform should think**.
---
# What is an Agent?
This project does **not** build a chatbot.
It builds an **Infrastructure Investigation Agent**.
The primary objective is not to answer questions.
The primary objective is to collect reliable operational evidence and produce accurate assessments.
---
# Core Philosophy
The platform follows one fundamental principle:
> **Code investigates. AI explains.**
Infrastructure investigation should be deterministic whenever possible.
Artificial Intelligence should only be responsible for interpreting collected evidence.
---
# Separation of Responsibilities
The platform separates investigation from assessment.
```
Investigation
↓
Evidence
↓
Assessment
```
These responsibilities should never overlap.
---
# Investigation
Investigation is deterministic.
Its purpose is to answer questions such as:
- What should be inspected?
- Where should evidence be collected?
- Which capabilities should be executed?
- Can execution happen in parallel?
- Has enough evidence been collected?
Investigation should be implemented using deterministic code.
---
# Evidence
Evidence is the product of investigation.
Evidence should be:
- accurate
- deterministic
- normalized
- composable
- benchmarkable
Evidence is more valuable than raw command output.
Whenever possible, tools should return operational evidence instead of raw data.
---
# Assessment
Assessment begins only after evidence has been collected.
The Assessment Model is responsible for:
- interpreting evidence
- identifying relationships
- explaining findings
- evaluating operational impact
- producing recommendations
The Assessment Model never performs infrastructure investigation.
---
# Code Before AI
Whenever deterministic logic can solve a problem, deterministic logic should always be preferred.
Examples include:
- intent resolution
- target resolution
- capability selection
- evidence planning
- execution scheduling
- batching
- parallel execution
- severity calculation
AI should never replace deterministic logic.
---
# Evidence Before Reasoning
Improving evidence quality provides greater value than improving prompts.
Preferred order:
```
Better Tool
↓
Better Evidence
↓
Better Assessment
```
Avoid compensating poor evidence with:
- larger prompts
- additional reasoning
- larger models
---
# Deterministic Execution
Infrastructure operations are generally predictable.
Examples include:
- checking installed software
- reading service status
- collecting hardware information
- querying monitoring systems
- inspecting configuration
These operations should always be deterministic.
---
# AI is the Last Step
The language model should receive completed evidence rather than controlling execution.
Preferred workflow:
```
Question
↓
Investigation
↓
Evidence
↓
Assessment
↓
Response
```
Avoid:
```
Question
↓
LLM
↓
Tool
↓
LLM
↓
Tool
↓
LLM
```
Multiple reasoning loops increase:
- token usage
- latency
- execution cost
- planning errors
---
# Composite Capabilities
Infrastructure questions rarely require a single observation.
Prefer capabilities that answer operational questions.
Example:
Instead of
```
CPU
Memory
Disk
Network
Services
```
Prefer
```
Machine Assessment
```
Composite capabilities reduce:
- iterations
- planning complexity
- prompt size
---
# Parallel Execution
Independent evidence should be collected simultaneously whenever practical.
Prefer:
```
CPU
Memory
Disk
Network
Services
↓
Merge
```
instead of sequential execution.
Parallel execution improves:
- latency
- token efficiency
- investigation consistency
---
# The Role of AI
AI is not the investigator.
AI is the analyst.
The platform should become more intelligent by improving deterministic investigation rather than increasing AI reasoning.
---
# Long-Term Vision
The ideal platform behaves as follows:
```
User
↓
Intent
↓
Target
↓
Evidence Plan
↓
Execution
↓
Evidence
↓
Assessment
↓
Final Response
```
Investigation becomes increasingly deterministic over time.
AI remains responsible only for interpreting evidence that deterministic execution cannot fully explain.
---
# Final Principle
The platform should evolve by improving code rather than relying on larger language models.
Every improvement should move work from AI into deterministic execution whenever practical.
