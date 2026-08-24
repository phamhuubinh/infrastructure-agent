# ADR 0004 — Project adds a RAG source

## Decision

A Project owns a persistent project-scoped document knowledge source.

The source is automatically available to conversations associated with that project.

## Constraint

Retrieval cannot cross project boundaries unless a future explicit cross-project feature is designed.
