# ADR-0010 — Deterministic external verification

# Status

Accepted; semantic-routing boundary amended after the primary cutover.

---

# Context

General-purpose requests include stable knowledge, live infrastructure facts,
and time-sensitive public facts. A current answer based only on model memory
is unsafe, while unrestricted model web/tool calling would make execution,
limits, and provenance non-auditable. The semantic planner may recognize that
fresh external evidence is required, but verification authority remains in the
harness.

---

# Decision

For the primary path, the bounded semantic planner classifies high-level
domain/freshness/source intent. The harness validates those typed semantics.
Stable general knowledge can be answered without collectors; live environment
requests use the deterministic investigation pipeline; validated
current/external requests and explicit public URLs use the deterministic
external-verification path.

External verification remains the fixed flow `search -> deterministic select
-> fetch -> canonical evidence -> model explanation`. `InternetTool` provides
the provider-neutral `web_search` contract plus hardened `web_fetch`. The
planner/assessment model does not receive a direct web-tool API and cannot
choose a provider, bypass URL validation, control retries, or expand the
verification budget. Explicit user URLs and typed source constraints are hard
inputs validated by code.

Search and fetch share public-URL validation, DNS pinning, redirect checks,
timeouts, response-size limits, per-request budgets, short-lived valid-only
caching, and credential-safe provenance. Source directives are typed hard
constraints; unavailable required sources fail closed. Missing or failed
external evidence is `UNKNOWN`/unavailable, not a positive risk or a verified
current claim. Planner/model failure never falls back to model memory as if it
were verified current information.

---

# Consequences

## Positive

- Natural-language currentness recognition can use the semantic planner while
  source enforcement, cost, and stop conditions remain repeatable.
- Each external answer can render URL/provider/retrieval provenance.
- Web failures and SSRF attempts stop safely without an ungrounded fallback.
- General writing and code generation remain available without being confused
  with an executed infrastructure action.

## Costs

- A configured search endpoint is required for query-based current facts.
- Currentness/source semantics depend on a valid typed plan; malformed,
  unavailable, or unsupported planning fails closed rather than using the old
  lexical router.
- Dynamic sites that require JavaScript, login, or browser automation are out
  of scope.

## Rejected alternatives

- **Unrestricted model web/tool loops:** rejected because execution, URLs,
  retries, and stopping behavior cannot be reviewed reliably.
- **Treat search snippets as verified evidence:** rejected because a snippet
  is not the referenced page content.
- **Model-memory fallback for current facts:** rejected because it can be stale
  while sounding verified.

---

# Related records

- `ADR-0002-llm-assessment-only.md`
- `ADR-0008-evidence-validity.md`
- `docs/tools/internet.md`
