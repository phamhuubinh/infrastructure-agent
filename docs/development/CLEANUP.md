# Cleanup and Repository Hygiene

Cleanup is a required phase of the refactor, not optional polish.

## Goal

After the new architecture is the only configured primary path, remove code,
files, flags, tests, imports, and folder structure that exist only for the
superseded architecture.

## Evidence before deletion

Do not delete by filename guess. For each candidate:

1. find imports and runtime callers;
2. identify tests that exercise it;
3. identify configuration/feature flags that instantiate it;
4. identify CLI/API/setup/compatibility callers;
5. migrate any still-valid responsibility;
6. delete only when the remaining graph proves it is unnecessary.

## Likely cleanup categories

Reevaluate and remove when no longer required:

- lexical natural-language intent routers;
- semantic target/source parsers used before the model;
- freshness/currentness keyword detectors;
- mutation keyword routers used as primary authority;
- lexical follow-up/session selectors;
- legacy semantic planner orchestration;
- duplicate action/execution contracts;
- compatibility adapters with no callers;
- superseded feature flags;
- tests that lock old architecture rather than current behavior;
- stale generated fixtures;
- duplicate response/finalization paths;
- old documentation and architecture terminology.

## Move useful code instead of deleting it

Some old components may contain useful deterministic implementation. Preserve
that behavior in the correct subsystem when appropriate, for example:

- reviewed Linux collectors;
- Grafana/Zabbix clients and parsers;
- Internet SSRF/network protections;
- evidence normalization/provenance;
- redaction;
- storage;
- existing Project retrieval logic;
- typed errors and result contracts.

The goal is to delete the obsolete responsibility, not throw away proven tool
implementation.

## File placement

A file is misplaced when its primary responsibility belongs to another
subsystem. During cleanup:

- model-provider code lives with model adapters;
- capability-specific behavior lives with that capability/tool;
- permission/approval logic lives in execution policy;
- evidence contracts live in evidence;
- Project/RAG lifecycle lives in projects/retrieval;
- event filtering/storage lives in events;
- API/CLI should be thin application boundaries.

Avoid generic `utils.py` dumping grounds and giant coordinator modules.

## Completion criteria

Cleanup is complete when:

- configured runtime does not import the legacy semantic stack;
- dead modules have no callers and are removed;
- duplicate architecture concepts are gone;
- source layout matches responsibility boundaries;
- stale tests/flags/config are removed;
- static checks and full QA pass;
- repository-wide search finds no misleading legacy architecture terminology
  except intentional migration/history references.
