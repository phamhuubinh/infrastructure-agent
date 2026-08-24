# Manual QA runners

These runners may start Docker or make real model/tool requests.

```bash
make qa-smoke
python3 scripts/qa/ga2_runner.py --mode smoke --fail-fast

make qa-full
python3 scripts/qa/unified_qa.py
```

## GA2 runtime contract

GA2 is an HTTP black-box runner against the public packaged API path.

Implemented Safety P0 checks include hidden-reasoning marker leakage, failed/empty HTTP behavior, required REFUSE for selected protected fixtures, unknown-target execution, and hard-source preservation where applicable. Do not describe that fixture set as a proof against every possible secret leak.

Runtime viability reads `execution_trace.runtime_metrics.canonical_runtime` plus public `steps`.

## Tool success semantics

`budget.actions_used` is a budget/dispatch counter. It is **not proof of successful tool evidence**.

A metric named successful tool execution must be derived from successful public execution/evidence observations with relevant capability/source/provenance data. Report attempted/dispatched/failed/succeeded separately.

Until fixed, historical viability fields derived only from `actions_used` are not authoritative success metrics. See F-11 in `docs/development/IMPLEMENTATION_GAPS.md`.

## First-failure rule

If live QA fails, inspect the first real canonical failure/observation. `--fail-fast` may make viability non-representative after an early P0. Do not raise model/action limits to hide loops.
