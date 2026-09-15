# ADR 0007 — Direct canonical registry exposure

## Status

Accepted. This supersedes the former progressive model-facing schema exposure decision.

## Decision

Chat and Project supply every registered model-callable tool schema from the one canonical
`ToolRegistry` on the initial model turn. This is not a semantic router: the model still
decides whether and which tools to call.

`ToolRunner`, `RuntimeScope`, input validation, mutation authorization, and exact mutation
allowlisting remain application-owned and complete regardless of model schema visibility.
Seeing a mutation schema never authorizes execution.

The runtime reports the complete provider tool-schema byte size. A registry that cannot fit the
focused context limit is a measured failure, not a reason to restore progressive exposure.

## Superseded architecture (historical)

The former ADR 0007 used `orion.tools.expand` for request-local schema discovery and
`exposed_for_retry` for calls made before exposure. These mechanisms are retired; this
paragraph documents migration history only, not current runtime behavior.
