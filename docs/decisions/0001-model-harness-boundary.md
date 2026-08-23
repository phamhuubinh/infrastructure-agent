# ADR-0001 — Model/Harness Responsibility Boundary

**Status:** Accepted

## Decision

The model owns natural-language understanding, reasoning, and next-action
proposals. The harness owns authority, validation, execution, evidence,
resource limits, and completion.

A model ACTION is untrusted until validated. The model does not receive raw
execution authority.

## Consequence

Changing models may change interpretation and strategy but cannot create new
permissions, targets, sources, capabilities, credentials, or execution powers.
