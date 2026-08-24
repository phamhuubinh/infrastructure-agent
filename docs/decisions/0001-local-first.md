# ADR 0001 — Local-first

## Decision

Orion is designed to run locally by default.

Core application services, persistence, project data, and RAG/indexing should be locally deployable. External models and external data systems are integrations, not architectural requirements.

## Consequence

The architecture should not be driven by cloud quota/rate-limit assumptions.
