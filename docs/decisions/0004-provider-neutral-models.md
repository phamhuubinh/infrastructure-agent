# ADR-0004 — Provider-Neutral Model Layer

**Status:** Accepted

## Decision

Orion uses one model interface with provider adapters. The architecture must
support cloud APIs and local runtimes without changing agent semantics.

Supported/provider-target examples may include OpenAI, Anthropic, OpenAI-
compatible endpoints, Ollama, vLLM, Qwen, CPU-local models, and future
providers.

## Consequence

Provider-specific behavior stays at the adapter boundary. Core contracts favor
simple portable structured output.
