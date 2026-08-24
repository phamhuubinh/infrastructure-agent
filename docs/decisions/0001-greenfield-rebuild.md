# ADR-0001: Greenfield rebuild inside the existing repository

Status: Accepted

## Decision

Treat the new Orion architecture as a clean-sheet rebuild. Existing code is audited for reusable components but does not constrain protocol, module boundaries, persistence shape, or compatibility unless an external requirement is explicitly documented.

## Consequence

Large deletion and replacement is expected. Parallel old/new runtimes are temporary migration mechanisms only and must have a removal date/gate.
