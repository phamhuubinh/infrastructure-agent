# ADR-0008: Provider-neutral model backend

Status: Accepted

## Decision

Core runtime depends only on canonical ModelTurn and tool definitions/results. Native OpenAI, Anthropic, and OpenAI-compatible/vLLM behaviors remain inside adapters. Provider structured output is never final authority.
