# Model Provider Architecture

## Goal

Orion must not depend architecturally on one model vendor or one local runtime.
Today a user may run Qwen locally; tomorrow the same installation may use
OpenAI, Anthropic, Ollama, vLLM, another OpenAI-compatible server, or a CPU-only
model.

## Provider-neutral interface

The agent core talks to a model interface that normalizes:

- connection/model identity;
- messages/input context;
- structured decision schema support;
- timeouts and cancellation;
- token/usage metadata when available;
- provider errors;
- optional reasoning configuration;
- streaming/activity support when available.

Provider adapters translate that common contract to vendor-specific APIs.

## Structured output

The controller protocol should be designed for portability:

- simple closed objects;
- readable field names;
- small decision enum;
- minimal nesting;
- no provider-specific schema tricks in core semantics;
- strict parser/validation after generation.

If a provider cannot guarantee native structured output, its adapter may use a
bounded text-to-structure mechanism, but the resulting decision must still pass
the same canonical parser.

## Model fallback

Fallback between configured models may be supported as runtime policy. Fallback
must not silently change permissions, capability authority, target/source
scope, or execution budgets.

## Model absence

Orion should still start and expose configuration/diagnostics when no model is
configured. Requests that require the agent model should return a clear setup
error rather than guessing a semantic route with deterministic keywords.

## Token efficiency

Token efficiency is achieved by bounded context, progressive capability
disclosure, compact observations, RAG retrieval, and chat-memory compaction.
Do not trade away protocol clarity merely to save a few field-name tokens.
