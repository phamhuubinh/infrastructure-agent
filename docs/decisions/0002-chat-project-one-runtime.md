# ADR 0002 — Chat and Project share one runtime

## Decision

Chat is the base runtime. Project reuses the same runtime and adds project context plus a project-scoped knowledge source.

## Rejected

Separate Chat agent, Project agent, or duplicated orchestration pipelines.

## Consequence

Tool behavior is identical across Chat and Project except that Project has additional knowledge available.
