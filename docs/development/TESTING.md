# Testing Strategy

Tests prove behavior and architecture boundaries.

## Required families

- **Stage/contract:** branch exclusivity, active allowed kinds, exact discovered/disclosed IDs, closed action schema, malformed/stage-forbidden provider output.
- **Authority/config:** unknown capability/target/source, malformed custom target file, backend typo, invalid arguments, permission/approval, no implicit localhost/source.
- **Loop:** direct FINAL, discovery→detail→action, observation→FINAL, recovery, CLARIFY/REFUSE, provider failure, repeated invalid-stage/discovery no-progress, budget exhaustion.
- **Completion/evidence:** false final after failed/stale/blocked observation, tool-never-ran claim, target/source mismatch, deterministic mismatch, valid evidence-backed final.
- **Protected information:** multilingual/adversarial requests to reveal protected prompts/policies/secrets produce canonical REFUSE without a production keyword router.
- **Context/memory:** aggregate budget, UTF-8, complete current request, summary retention, attachment-heavy context, explicit oversize behavior.
- **Sessions/persistence:** SQLite/PostgreSQL list/delete/clean parity, confirmation-before-mutation, query/delete/new-query race, no resurrection/fork, corruption preservation, DB-pool permit/rollback invariants.
- **RAG:** project isolation, deletion, retrieval/provenance, standalone auth/exposure/SSRF/rebinding/redirect policy, fault injection across file/vector/BM25/metadata.
- **Model/provider:** active schema propagation/validation, structured-output fallback, timeout/error, configured identity grounding, health-state transitions.
- **Events/metrics:** production correlated events, counters actually change, dispatched failure != success, redaction/bounds.
- **UI:** exact session+generation token, stale timers, real attachment flow or absent affordance, health body semantics, destructive confirmation.
- **GA2:** successful tool execution counted from successful evidence observations, with all-error/blocked/unavailable/mixed cases.

## Validation gates

Local unit/static validation and live Docker/model/GA2/E2E validation are separate. Broad/destructive repairs should run the full local unit/static suite when practical. Live validation is only run when explicitly requested.

When live/full QA fails, isolate the first real failure before chasing cascades.
