# ADR-0004: Dynamically expose capabilities

Status: Accepted

## Decision

Do not send the full capability catalog to every model call. Use a small discovery/tool-search surface, then expose exact reviewed tools with exact schemas. Registered-but-unexposed capabilities are not callable.
