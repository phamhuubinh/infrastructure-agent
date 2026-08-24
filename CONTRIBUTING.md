# Contributing to Orion

Contributions must move the repository toward the target architecture, not add another compatibility layer around the previous runtime.

## Before coding

Read `docs/README.md`, relevant architecture documents, and `docs/development/ENGINEERING_RULES.md`. For major work, also read `docs/development/CODE_AUDIT_BRIEF.md` and `REBUILD_PLAN.md`.

## Pull request expectations

A change should state:

- target contract being implemented;
- old components kept, adapted, rewritten, or deleted;
- security/authority impact;
- tests executed and tests not executed;
- migration or persistence impact;
- remaining gaps.

Architecture changes require an ADR in `docs/decisions/`. Implementation convenience is not sufficient reason to weaken exact authority, evidence integrity, or execution isolation.

## Validation

Prefer contract and vertical-slice tests. Fake-model tests prove deterministic harness behavior; they do not prove live-model usability. Live-model gates are separate and must be recorded as such.
