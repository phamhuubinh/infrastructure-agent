# Current Implementation Gaps and Repair Ledger

> **Purpose:** one concrete repair checklist for confirmed current defects/gaps.
>
> **Architecture authority:** this is not an ADR. Accepted target design remains `docs/decisions/` → `docs/architecture/` → engineering rules.
>
> **Audit snapshot:** 2026-08-24. Blind audit reported 552 tracked files; 543 relevant files read/audited; 9 generated/vendor/binary files intentionally skipped; 0 relevant files unaccounted. The audited worktree was GitHub `main` `3e88075` plus seven pre-existing local modifications.
>
> **Completeness:** exhaustive static/cross-reference coverage does not prove that no additional bug exists. Provider/runtime/environment/timing behavior still requires targeted/live evidence.

## Repair rules

- Fix root causes, not individual QA phrases.
- Do not add a deterministic semantic router.
- Do not increase retry/model-call limits to hide loops.
- Do not weaken exact authority.
- Preserve unrelated dirty changes.
- Add regression tests for every repaired item.
- Mark resolved only after relevant checks actually pass.

## P1

### F-01 — RESOLVED: Final answers are validated against execution evidence

Canonical runtime can accept model `FINAL` immediately; output sanitation does not verify objective execution claims. Add deterministic completion validation for execution/status/target/source/freshness/deterministic result/provenance without semantic re-routing.

### F-02 — RESOLVED: Invalid target configuration fails closed

`TargetStore`/config validation can synthesize local execution on malformed/unknown target config and may validate repo-root targets rather than the actual `ORION_TARGETS_FILE`. Validate the actual selected file, close backend types, fail closed, and allow localhost only through explicit valid bootstrap/config.

### F-03 — RESOLVED: PostgreSQL pool permit and connection recovery

Release permits when connection creation fails; rollback/validate or discard failed SQL connections. Add permit/transaction failure-injection tests.

### F-04 — RESOLVED: CLI session deletion/clean confirmation and persistence parity

Confirm before mutation. Route list/delete/clean through one persistence-aware service for SQLite/PostgreSQL. Cancel must perform no mutation.

### F-05 — RESOLVED: Standalone RAG authentication and proxy boundary

Standalone RAG/Qdrant ports are published; project/document operations lack a hardened auth boundary; request-scoped analysis can accept arbitrary model endpoint + bearer secret. Bind development exposure to loopback or add auth/mTLS, secure vector admin, and enforce outbound destination/DNS/private-IP/redirect policy.

### F-06 — RESOLVED: Query/delete race cannot resurrect/fork a session

Resolved repository-local lifecycle coverage: stable lifecycle leases/tombstones
coordinate SQLite and PostgreSQL-backed stores; deterministic storage-fake tests
cover queued old-generation rejection, in-flight delete ordering, same-ID new
generation, and clean-all invalidation. Live PostgreSQL remains a separate
environment gate.

### F-07 — RESOLVED: Corrupt persistence metadata is preserved

Preserve/quarantine corruption; fail closed/read-only for mutation until explicit recovery. Do not destroy recovery evidence.

### F-08 — RESOLVED: Checked-in CI contract is current and locally green

Resolve exact Ruff/mypy diagnostics and stale nonexistent `tests/qa/test_transcript_regression.py` workflow reference. Validate explicit workflow paths.

## P2

### F-09 — RESOLVED: Stage-specific response schema is harness-enforced

Local work improves provider schemas, but parser/runtime can still accept stage-forbidden kinds or treat a known registry capability as selected without proving prior disclosure. Validate parsed decision against active stage/schema; track actual disclosed groups/capabilities; exact selected-detail schema; repeated invalid cycles count as no-progress.

**Live symptom:** invented first-stage `ACTION` IDs (`system_prompt`, `calculator`) and model-call feedback loops.

### F-10 — RESOLVED: Conversation context uses one bounded aggregate budget

Use one aggregate serialized/token allocator: complete current request + summary first, then recent turns/attachments. Do not silently truncate a user request into a different request.

### F-11 — RESOLVED: GA2 distinguishes dispatch from successful evidence

`budget.actions_used` is dispatch/budget state, not success. Count successful public evidence observations and report attempted/dispatched/failed/succeeded separately.

### F-12 — RESOLVED: Model availability and health are distinct end-to-end

Replace hardcoded availability with explicit not-configured/unknown/healthy/unhealthy. Test before activation or rollback on failure. UI must inspect semantic health body/state, not just HTTP 200.

### F-13 — RESOLVED: Idle timer is scoped to chat session and generation

Bind timers/abort/update to exact session ID + generation token; ignore stale callbacks.

### F-14 — RESOLVED: Document response headers are filename-safe

Reject CR/LF/control characters and use framework/RFC 5987-safe `Content-Disposition` construction.

### F-15 — RESOLVED: Unified event stream and metrics

The canonical session/runtime path now emits one redacted, correlated
`AgentEvent` stream across request/model/discovery/authority/execution/evidence
and completion. `/api/metrics` projects its counters from that stream; it no
longer reconstructs events from runtime summary counters or maintains a second
manual metric truth.

### F-16 — RESOLVED: Legacy semantic-routing/config/persisted state removed

Caller analysis confirmed no production caller for the lexical request
semantics/frame/routing/multi-intent/evidence-requirement/fact-reconciliation
stack, its response-strategy budget/trace types, or session-investigation
state. Those modules, rollout flags, writers, and obsolete tests are removed.
The canonical reviewed Internet executor and deterministic evidence
normalization remain. Existing JSON/SQLite/PostgreSQL session records with the
former `investigation_context` field still load; the field is ignored and no
longer written or migrated. **Never reconnect the legacy semantic stack.**

### F-19 — RESOLVED: Project/RAG multi-store recoverability

Upload uses staged files plus a durable recovery journal, atomic promotion, and
metadata-last visibility. Document/project delete write durable tombstones before
destructive index/file/metadata cleanup. On restart or next project access,
idempotent recovery either completes cleanup or retains the persistent degraded
record; normal reads never present tombstoned/partial documents as healthy.

## P3

### F-17 — RESOLVED: Chat attachments are bound to the active session

Implement real upload/session binding/progress/error, or remove the affordance/copy.

### F-18 — RESOLVED: Destructive UI actions require confirmation

Reuse explicit confirmation UI. Cancel=no request; confirm exactly once; pending disables duplicate action.

## Additional live-runtime issues

### L-01 — RESOLVED: Session construction uses the canonical model backend

GitHub `3e88075` `AppState.get_or_create_session()` still references legacy `agent.assessment_model`; `CanonicalSessionAgent` exposes `model_backend` and installs the summarizer through its conversation-store setter. The current local dirty tree has a narrow fix plus regression test; preserve/verify it.

### L-02 — RESOLVED: Model identity is grounded in configured metadata

A canonical direct identity question returned GPT-4/OpenAI while the configured runtime was Qwen. Ground identity in configured provider/model metadata; never trust model self-identification.

### L-03 — REQUIRES LIVE VALIDATION: Protected-instruction request refusal

A system-prompt reproduction request has returned FINAL, looped to model-call limit, and after local first-stage schema work produced semantically wrong `DISCOVER calculator`. Apply ADR-0009 + clear protocol semantics + deterministic stage enforcement; do not hardcode language keywords.

### L-04 — REQUIRES LIVE VALIDATION: GA2 model-call loop behavior

A 34-case smoke run observed 18 canonical `model_call_limit` failures and zero successful tool execution under the then-current metric. Treat F-09/no-progress/provider-protocol compatibility as root-cause candidates and trace the first remaining real tool case after static repair. Do not increase `max_model_calls` as the fix.

## Broad repair completion

1. Every F/L item fixed or explicitly deferred with reason.
2. Exact CI lint/type/test commands green.
3. Full local unit/static suite green.
4. `git diff --check` clean.
5. Static reachability proves legacy semantic code removed/not reconnected.
6. Regenerate OpenAPI when API contracts change.
7. Live runtime/GA2 only when explicitly requested.
8. When live GA2 runs, success metrics come from successful evidence and the first remaining real failure is isolated.
