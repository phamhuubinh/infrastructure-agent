# Cleanup and Repository Hygiene

> **Baseline:** at `259f85b`, the superseded deterministic/semantic routing stack is removed from the
> configured Web/CLI Chat hot path. These rules remain mandatory for future cleanup and for proving
> that compatibility code is truly dead.

Cleanup is a required phase of architecture work, not optional polish.

## Goal

After a new architecture becomes the configured primary path, remove code, files, flags, tests,
imports, documentation, and folder structure that exist only for the superseded responsibility.

Do not delete proven tool/evidence/runtime behavior simply because it was previously called by an
old orchestration layer.

## Evidence before deletion

Do not delete by filename guess. For each candidate:

1. find imports and runtime callers;
2. identify tests that exercise it;
3. identify configuration/feature flags that instantiate it;
4. identify CLI/API/setup/compatibility callers;
5. migrate any still-valid responsibility;
6. delete only when the remaining graph proves it is unnecessary.

## Legacy categories to reject on the canonical hot path

Remove or refuse to recreate, when no real compatibility caller requires them:

- lexical natural-language intent routers;
- semantic target/source parsers used before the model;
- freshness/currentness keyword detectors;
- mutation keyword routers used as primary authority;
- lexical follow-up/session selectors;
- legacy semantic planner orchestration;
- duplicate action/execution contracts;
- compatibility adapters with no callers;
- superseded feature flags;
- tests that lock old architecture instead of current contracts;
- stale generated fixtures;
- duplicate response/finalization paths;
- stale documentation and architecture terminology.

Historical changelog/migration references may retain old terminology when they are clearly marked as
history.

## Preserve useful deterministic implementation

Move proven behavior behind the correct canonical subsystem where appropriate:

- reviewed Linux collectors;
- Grafana/Zabbix clients and parsers;
- Internet SSRF/network protections;
- evidence normalization/provenance;
- redaction;
- storage;
- Project retrieval logic;
- typed errors/results.

The goal is to remove obsolete semantic responsibility, not deterministic safety or proven
integration code.

## File placement

A file is misplaced when its primary responsibility belongs to another subsystem:

- model-provider code belongs with provider adapters;
- capability-specific behavior belongs with that capability/tool;
- permission/approval logic belongs at the execution authority boundary;
- evidence contracts belong with evidence;
- Project/RAG lifecycle belongs with projects/retrieval;
- event filtering/storage belongs with events;
- API/CLI remain thin application boundaries.

Avoid generic dumping grounds and giant coordinator modules.

## Completion checks for destructive cleanup

At minimum:

```bash
git grep -n "<legacy symbol or module>"
python3 -m pytest --collect-only -q
git diff --check
```

Then run targeted tests and the full local suite appropriate to the refactor. Live Docker/model/GA2
validation is a separate runtime gate and should be run only when explicitly intended.

Cleanup is complete for a scope when:

- the configured runtime does not import the superseded semantic path;
- dead modules have no callers and are removed;
- duplicate architecture concepts are gone;
- stale tests/flags/config are removed;
- repository-wide search finds no misleading active terminology except intentional history;
- static checks and required tests pass;
- runtime QA, when part of the release gate, validates the canonical path without restoring legacy
  behavior.
