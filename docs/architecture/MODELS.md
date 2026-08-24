# Model Provider Architecture

Orion uses a provider-neutral model interface for configured identity, input, structured decision schema, timeout/cancellation, usage/error metadata, and provider-specific translation.

## Structured output

Use simple closed portable schemas. Strict parsing is followed by strict validation against the **active stage/schema**. Native structured output is an optimization, not an authority boundary.

OpenAI-compatible canonical calls omit `max_tokens` and
`max_completion_tokens`, allowing the configured provider/model to determine
generation termination. Orion retains aggregate input-context budgets and all
runtime safety limits. A provider that requires an output parameter at its own
API boundary (currently Anthropic Messages) uses explicit provider-required
configuration rather than an Orion default ceiling.

## Model identity

A model is not a reliable source of truth about its own deployment identity. User-visible provider/model claims must be grounded in Orion's configured connection metadata. If unavailable, say unknown rather than inventing GPT/OpenAI/Qwen/etc.

## Health state

Configuration and health are separate:

```text
not_configured
configured_unknown
healthy
unhealthy
```

Do not hardcode `available=true` because a connection exists. Activation policy is explicit: test before activation or roll back on failed validation. UI must inspect semantic health state, not only HTTP 200/transport success.

## Fallback/absence

Model fallback may not widen authority. No-model mode returns setup error for model-requiring requests, not legacy keyword routing.
