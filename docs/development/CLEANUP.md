# Cleanup rules

Delete aggressively only after replacement and reachability are understood.

## Delete candidates

- old model-visible decision FSM/state types;
- semantic pre-routing/planning layers;
- action-selection/action-detail protocol code;
- completion-obligation machinery made unnecessary by evidence references;
- tool-family-specific authority bridges replaced by CapabilityDefinition;
- duplicate event/metrics systems;
- stale feature flags and rollout compatibility;
- tests that assert obsolete protocol behavior;
- generated artifacts that no longer match public API.

## Before deletion

- search imports/callers;
- inspect config and persistence references;
- inspect CLI/Web/QA use;
- decide data migration requirement;
- add replacement tests;
- run static reference checks.

## After deletion

- no dead compatibility shim unless external contract requires it;
- `git diff --check` clean;
- lint/type/unit tests green;
- regenerate generated artifacts from the new source of truth.
