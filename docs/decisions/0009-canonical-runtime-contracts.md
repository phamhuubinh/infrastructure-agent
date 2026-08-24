# ADR 0009: Canonical runtime contracts

## Status

Accepted target decision.

## Decision

Orion uses one canonical set of runtime identities for model turns, tool definitions/calls/results/errors, runtime scope, knowledge sources, documents, retrieved segments, citations/source references, and public timeline items.

Provider adapters and tool implementations map into these contracts rather than defining competing core representations.

`docs/architecture/CONTRACTS.md` is the authoritative architectural definition.

## Rationale

Without canonical contracts, provider adapters, RAG, API DTOs, persistence, and tool families can independently invent shapes for the same concept. That recreates hidden routing/state coupling and makes the runtime difficult to reason about.

## Consequences

- provider-native objects stop at the adapter boundary;
- tool implementation objects stop at the ToolRunner boundary;
- Chat and Project share the same contracts;
- persistence/API formats may differ physically but must map losslessly to the canonical semantics.
