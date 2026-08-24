# Model architecture

## Provider neutrality

The runtime depends on a small `ModelBackend` interface, not on OpenAI-, Anthropic-, or vLLM-specific response objects.

Canonical output:

```python
ModelTurn = ToolCall | FinalMessage | Clarification | Refusal
```

Canonical input contains:

- stable system instructions;
- bounded conversation context;
- tool results;
- currently exposed tool definitions;
- optional structured final schema.

## Native tools first, fallback second

When a provider supports reliable native tool calling, use it. Otherwise use a strict JSON fallback that expresses only the canonical model turn, not an Orion-internal workflow FSM.

Provider adapters must normalize:

- OpenAI Responses/native tool calls;
- Anthropic tool-use blocks;
- OpenAI-compatible/vLLM structured JSON or tool-call formats.

## Stable prompt prefix

Keep stable policy/instructions in a cache-friendly system prefix. Dynamic request state, tools, and tool results belong in later messages/fields.

## No provider authority

Provider-side JSON schema or guided decoding is generation assistance. Runtime parsing and harness validation remain authoritative.

## Model identity

Configured provider/model metadata is the source of truth for identity. Model self-description is not trusted machine state.

## Context limits

The context builder must allocate one aggregate budget across system policy, user request, summary/history, project retrieval, tool definitions, and tool results. Never silently truncate the current user request into a different request.

## Reasoning privacy

Private chain-of-thought is not persisted or exposed as product evidence. Store concise decisions, tool calls, results, and user-visible explanations instead.
