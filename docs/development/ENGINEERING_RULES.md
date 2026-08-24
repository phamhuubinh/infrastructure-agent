# Engineering Rules

These rules are normative for implementation work.

1. **Model semantics, deterministic authority.** Do not parse natural-language intent/target/source/freshness/follow-up/tool choice in code before the model to choose an execution path.
2. **Natural language is not authority.** Only structured validated state authorizes execution.
3. **Stage legality is authority.** Track real progressive-disclosure state and validate every parsed model decision against the active stage/schema. Provider-native JSON schema is only a generation aid.
4. **READ/WRITE are effect classes.** Permission is based on reviewed capability effect.
5. **Fail closed.** Unknown/malformed targets, sources, capabilities, backend types, and configured authority files fail explicitly. No implicit localhost/source fallback.
6. **Provider-neutral core.** Provider-specific behavior stays in adapters.
7. **Protected internal information.** Credentials never enter model context. Requests to reveal system/developer prompts, hidden policy/internal instructions, secrets, or private reasoning use generic REFUSE policy, never a language keyword router.
8. **Tools own integrations.** Commands/API/transport/parsing remain behind reviewed capabilities.
9. **Evidence explicit.** Failed/missing/stale data is never healthy. Dispatched is not successful.
10. **Objective completion checks.** Verify execution/status/target/source/freshness/deterministic-result claims from structured state without semantic post-routing.
11. **One aggregate context budget.** Preserve complete current request + summary, then allocate recent turns/attachments.
12. **Persistence fails recoverably.** Preserve/quarantine corruption; use transactions/staging/tombstones/outbox/compensation for multi-store mutations.
13. **Session lifecycle synchronized.** Query/delete/clean coordinate through stable per-session lifecycle state; deletion cannot race a writer into resurrection/fork.
14. **Model health != configuration existence.** Use unknown/healthy/unhealthy explicitly.
15. **One real event/metric model.** UI activity, traces, and counters derive from actual events; no fabricated/hardcoded state.
16. **No private reasoning logs.** Persist decisions/actions/status/evidence/timings only.
17. **Legacy semantic code is temporary.** Delete only after caller/import/config analysis; never reconnect it to production.
18. **No speculative scaffolding.** Avoid unused abstractions/future-tool stubs.
19. **Tests enforce architecture.** Cover stage legality/disclosure, exact authority, fail-closed config, evidence-backed finals, context budgets, persistence/session races, model health, events/metrics, provider compatibility.
20. **Current repair ledger.** Resolve `IMPLEMENTATION_GAPS.md` toward these rules and accepted ADRs, then mark/remove resolved entries.
