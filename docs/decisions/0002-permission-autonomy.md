# ADR-0002 — READ/WRITE and Autonomy

**Status:** Accepted

## Decision

Executable capabilities have one effect class: READ or WRITE.

User execution modes are:

- READ: reads automatic, writes blocked;
- RW + ASK: reads automatic, writes require scoped approval;
- RW + FULL: reads and validated writes automatic.

READ includes any reviewed operation whose effect is observation only,
regardless of whether the implementation uses shell, HTTP, database access, or
another transport.

## Consequence

Permission logic stays small and can evolve independently of model semantics.
