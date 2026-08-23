# ADR-0006 — No Semantic Pre-Router on the Configured Agent Path

**Status:** Accepted

## Decision

Normal configured requests go to the model without a language-specific code
layer first deciding intent, target, source, freshness/currentness, mutation
meaning, tool family, or follow-up meaning.

The model expresses semantic choices through structured decisions. The harness
then validates exact identifiers, schemas, permissions, and safety.

## Consequence

Adding human languages does not require adding another semantic router in code.
Legacy lexical routing can remain only on explicit compatibility surfaces until
removed.
