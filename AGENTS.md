# AGENTS.md — Repository instructions for Orion

## 1. Read project context first

Read, when relevant:

1. `docs/README.md`
2. relevant accepted ADRs in `docs/decisions/`
3. relevant `docs/architecture/`
4. `docs/development/ENGINEERING_RULES.md`
5. `docs/development/IMPLEMENTATION_GAPS.md`
6. relevant migration/testing/cleanup docs
7. `README.md`
8. relevant implementation/tests

Source/tests/generated schema/runtime evidence establish current implementation facts. ADRs establish target architecture. `IMPLEMENTATION_GAPS.md` is a repair ledger, not architecture authority.

## 2. Core architecture rules

- Model owns language semantics/reasoning/next-action proposals.
- Harness owns stage legality, actual progressive-disclosure state, exact authority, execution, evidence, limits, no-progress handling, and completion.
- Do not add a prose semantic pre-router for intent, target, source, freshness, mutation, tool family, or follow-up.
- Natural-language text never authorizes execution.
- Validate parsed model output against the active stage/schema even after provider-native structured output.
- An invented registry capability ID is not disclosed authority.
- Exact capability/target/source resolution only; malformed configuration fails closed; no implicit localhost/source fallback.
- READ/WRITE is reviewed capability effect, not keyword classification.
- Tools own shell/HTTP/database implementation; model never receives arbitrary primitives or credentials.
- Preserve evidence status/time/target/source/provenance. Attempted/dispatched is not the same as successful.
- Objective final execution claims must be checked against structured evidence.
- System/developer prompts, hidden policies/internal instructions, credentials/secrets, and private hidden reasoning are protected. Requests to reveal/reproduce them use `REFUSE`, not DISCOVER/ACTION.
- Model identity claims must come from configured model metadata, not model self-description.
- Do not resurrect legacy semantic routing/compatibility to satisfy tests.
- Remove dead compatibility/semantic code only after caller/import/config analysis proves it is unused.

## 3. Validation policy

By default run the smallest relevant local unit/contract/static checks.

For a broad/destructive repository repair, also inspect callers/imports/static references, run `git diff --check`, and run the full **local unit/static suite** when practical.

Live Docker/model/GA2/E2E/benchmark/external-service validation is a separate gate. Do not cross it unless the user's current request explicitly asks for it.

When live/full QA fails, isolate the first real failure before chasing cascades. Never raise retry/model-call limits just to hide a no-progress loop.

## 4. Current repair rules

When resolving `IMPLEMENTATION_GAPS.md`:

- fix root causes, not QA-specific phrases;
- preserve corrupt persistence data for recovery instead of treating it as empty;
- synchronize delete/clean with in-flight session work;
- make multi-store mutations transactional or explicitly recoverable;
- represent model health as unknown/healthy/unhealthy instead of configured=true;
- scope UI generation timers/actions to exact session + generation token;
- use safe download header construction;
- wire real events/metrics or remove misleading surfaces;
- remove unreachable semantic code only after proving it is dead; never reconnect it.

## 5. Git/side effects

Do not commit/push/rebase/reset/stash/clean/create branches unless explicitly requested. Preserve unrelated dirty changes.

Do not automatically start Docker/servers/browsers, install system packages, modify credentials/.env, or delete/reset user data.

## 6. Documentation

When behavior changes, update current docs and mark/remove resolved entries from `IMPLEMENTATION_GAPS.md`. Regenerate OpenAPI through its generator rather than hand-editing it.
