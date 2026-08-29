# ADR 0007 — Registry-derived progressive tool exposure

## Decision

Every successfully registered/configured ordinary tool is discoverable in Chat and
Project through one deterministic catalog derived from the canonical registry.

The model uses one generic expansion control to request one or more exact catalog
names. Full schemas are then exposed only for that request's selected subset. The
model remains the semantic chooser; Orion does not pre-route prompts or provide a
user tool picker. An unexposed ordinary tool cannot execute.

## Future

The canonical registry, ToolRunner validation, RuntimeScope binding, and ToolResult
loop remain complete and unchanged by the model-facing projection.
