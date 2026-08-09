# ADR-0010 — Deterministic external verification

# Status

Accepted

---

# Context

General-purpose requests include stable knowledge, live infrastructure facts,
and time-sensitive public facts. A current answer based only on model memory
is unsafe, while unrestricted LLM tool calling would make queries, URLs,
limits, and provenance non-auditable.

---

# Decision

Orion classifies request semantics before any tool call. Stable general
knowledge goes to the model directly; live environment requests remain on the
existing deterministic investigation pipeline; current/external and explicit
URL requests use a deterministic external-verification policy.

External verification is the fixed flow `search -> deterministic select ->
fetch -> canonical evidence -> model explanation`. `InternetTool` provides a
provider-neutral `web_search` contract plus the existing hardened
`web_fetch`. The model receives fetched evidence but never chooses a provider,
capability, URL, retry loop, or command.

Search and fetch share public-URL validation, DNS pinning, redirect checks,
timeouts, response-size limits, per-request budgets, short-lived valid-only
caching, and credential-safe provenance. Source directives are typed hard
constraints; unavailable sources fail closed. Missing or failed external
evidence is `UNKNOWN`, not a positive risk or a verified current claim.

---

# Consequences

## Positive

- Currentness policy, source selection, cost, and stop conditions are
  repeatable and testable.
- Each external answer can render URL/provider/retrieval provenance.
- Web failures and SSRF attempts stop safely without an ungrounded fallback.
- General writing and code generation remain available without being confused
  with an executed infrastructure action.

## Costs

- A configured search endpoint is required for query-based current facts.
- Deterministic lexical currentness detection can miss unusual phrasings; any
  semantic expansion must remain schema-only and benchmark-gated.
- Dynamic sites that require JavaScript, login, or browser automation are out
  of scope.

## Rejected alternatives

- **Unrestricted LLM web/tool loops:** rejected because queries, URLs, and
  stopping behavior cannot be reviewed reliably.
- **Treat search snippets as verified evidence:** rejected because a snippet
  is not the referenced page content.
- **Model-memory fallback for current facts:** rejected because it can be
  stale while sounding verified.

---

# Related records

- `ADR-0002-llm-assessment-only.md`
- `ADR-0008-evidence-validity.md`
- `docs/tools/internet.md`
- Historical General Agent external-verification backlog (preserved in Git history)
