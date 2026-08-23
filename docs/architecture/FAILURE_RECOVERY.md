# Failure and Recovery

## Principle

When something fails, the model should receive a safe structured observation
and choose the best next step. The harness should not silently replace the
model's strategy with a hard-coded semantic fallback.

## Model choices after failure

Depending on the situation, the model may:

- try another registered capability;
- use another source;
- adjust valid arguments;
- collect more evidence;
- ask the user for missing information or help;
- explain a manual recovery step;
- finish with the best supported assessment;
- refuse if the requested operation is unavailable or not permitted.

## Runtime responsibilities

The deterministic runtime still owns:

- exact retry limits;
- transport retries explicitly defined by a tool;
- request deadlines;
- no-progress circuit breakers;
- permission enforcement;
- safety boundaries;
- typed error contracts.

A tool may have a fixed internal fallback sequence if that sequence is part of
the reviewed capability implementation. That is different from the harness
interpreting user semantics and switching to another unrelated capability.

## Error categories

Errors should be machine-readable enough for the model and diagnostics layer to
distinguish cases such as:

- invalid action;
- permission denied;
- approval required/declined;
- target/source unknown;
- dependency unavailable;
- authentication/credential failure without exposing the secret;
- timeout/network failure;
- unsupported environment;
- malformed provider output;
- model provider unavailable;
- tool collection/parsing failure;
- circuit breaker / budget exhaustion.

## No-progress handling

Repeated identical failures or repeated actions with no new evidence should
count as no progress. The runtime may stop the loop and ask the model to explain
or ask the user for help.

The exact thresholds are configuration and tests, not product semantics.
