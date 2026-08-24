# ADR 0008 — Provider-neutral model backend

## Decision

Core Chat/Project/tool runtime depends on provider-neutral contracts.

OpenAI-compatible local models are first-class. Other providers are adapters.

Provider-specific response types must not define Orion's core architecture.
