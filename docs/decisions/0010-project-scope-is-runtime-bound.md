# ADR 0010: Project scope is bound by Orion runtime

## Status

Accepted target decision.

## Decision

The model decides whether project knowledge is useful and what query/read operation to perform.

Orion determines the active Project from application/session state and binds that exact project identity into the tool execution context.

Ordinary model-facing knowledge calls do not gain cross-project access by supplying an arbitrary `project_id`.

## Rationale

Project identity is deterministic application state, not a semantic inference problem.

Allowing the model to choose arbitrary project scope would unnecessarily mix semantic tool choice with data-isolation responsibility.

## Consequences

- Project remains Chat + project-scoped knowledge, not a separate agent;
- the same knowledge tool can operate in Chat and Project through `RuntimeScope`;
- cross-project leakage can be tested deterministically;
- no semantic pre-router is introduced.
