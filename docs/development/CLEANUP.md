# Cleanup and Repository Hygiene

Cleanup removes superseded semantic responsibilities only after real caller/import/config analysis.

## Reject on canonical hot path

Lexical intent/target/source/freshness/mutation/follow-up routers, legacy semantic planner orchestration, duplicate contracts, no-caller compatibility adapters, obsolete flags/config/persisted semantic state, stale tests/docs.

## Current candidate set

F-16 in `IMPLEMENTATION_GAPS.md` records legacy semantic-routing/state components found unreachable by the 2026-08-24 blind audit. Re-run reachability after other repairs before deletion. Do not wire those components back into production.

## Preserve useful deterministic behavior

Reviewed collectors/clients/parsers, Internet SSRF controls, evidence/provenance, redaction, storage, retrieval internals, typed errors/results.

## Completion checks

```bash
git grep -n "<legacy symbol or module>"
python3 -m pytest --collect-only -q
git diff --check
```

Then targeted tests and, for broad/destructive repair, the full **local unit/static suite** when practical. Live Docker/model/GA2 is a separate explicit gate.
