# ADR-0002: Use a model-native tool loop

Status: Accepted

## Decision

The model interacts through ordinary tool calls and tool results. Internal harness states such as ACTION_DETAIL, OBSERVATION, FEEDBACK, or selection-as-action are not part of the model protocol.

## Rationale

Each model-facing concept should have one semantic meaning. Harness state belongs in the harness.
