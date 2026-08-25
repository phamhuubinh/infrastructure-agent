# ADR 0011 — Infrastructure target and mutation contracts

## Status

Accepted target decision.

## Decision

Linux, Grafana, and Zabbix join the existing `ToolRegistry` and `ToolRunner` as
explicit semantic operations with closed schemas. The model chooses an operation from
all registered tools; Orion deterministically validates it, binds `RuntimeScope`,
resolves a configured target, and executes it. Chat and Project continue to use the
same model/tool loop.

Each operation selects an integration target only through an exact `target_ref`.
This opaque, stable, non-secret reference maps server-side to connection details,
credential reference, and secret resolution. The model may be given sanitized target
names/refs as deterministic context, but never connection authority or credentials.

Mutation lifecycle, cancellation, retries, duplicate behavior, verification, errors,
provenance, and public activity are defined in `docs/architecture/CONTRACTS.md` and
the operation contracts in `docs/tools/`.

## Consequences

- no semantic pre-router, tool picker, enabled-tools field, infrastructure mode,
  approval engine, separate infrastructure runtime, or dynamic capability protocol is
  introduced;
- no model-facing generic shell, SSH command execution, generic Grafana HTTP request,
  or generic Zabbix JSON-RPC invocation is introduced;
- mutations use one ordinary ToolRunner dispatch and are never transparently replayed
  after their side-effect boundary;
- target/credential failures and uncertain outcomes remain explicit canonical errors;
- public activity is shown through the existing runtime timeline/events with safe
  metadata only.

## Rationale

Explicit semantic operations give Orion a small initial local-first infrastructure
surface without moving semantic decisions away from the model or leaking transport
authority into model arguments. A common mutation contract makes implementation and
testing deterministic while avoiding a new transaction or durable-idempotency system.
