# Deterministic reasoning v1 — compatibility and migration plan

## Goal and scope

This plan moves callers from ambiguous tuple/dict result handling to explicit
command, capability, evidence, Fact, and Finding contracts without a big-bang
API change. It applies to the Python runtime, tests, CLI/API step rendering,
and Child Tool implementations. It does not change the public query response
shape merely because a rollout flag is toggled.

## Contract matrix

| Boundary | Legacy shape | v1 shape | Compatibility during window | Owner/removal condition |
| --- | --- | --- | --- | --- |
| Execution backend → Linux capability | `(ok, output)` | `CommandResult` | `CommandResult.__iter__` preserves tuple unpacking and emits `DeprecationWarning`. Legacy backend tuples are recorded as structured outcomes by `LinuxTool`. | Backend/test callers; remove after no tuple unpacking remains outside adapter tests. |
| Child capability → Tool dispatcher | raw dict/list/string | `CapabilityResult` | `CapabilityResult.from_legacy()` maps raw payloads and detected command failures; direct use emits `DeprecationWarning`. Internal dispatcher bridges suppress duplicate warnings while legacy handlers are converted. | Child Tool owners; remove after every handler returns `CapabilityResult`. |
| Tool → runtime | `ToolResult(success, data, error)` | `ToolResult` plus status, command results, warnings, fact names, structured error, provenance fields | Fields are additive; legacy success/data/error stay available. | Runtime/UI callers; remove only after schema consumers use named fields. |
| Runtime → assessment | raw evidence dicts | `EvidencePackage` + Facts, failures, recovery, source links | `data`/`raw_data` remains available; Facts are additive and can be rollout-gated. | Assessment/UI callers; remove legacy evidence-name completeness only after all requirements use canonical metrics. |
| Deterministic reasoning | ad-hoc dict threshold reads | FactSet → atomic/composite Findings | `ThresholdEvaluator.evaluate(data)` remains a bounded compatibility adapter. | Rule callers; remove after all callers evaluate canonical FactSets. |

## Migration sequence

1. **Inventory and pin behavior.** Add/maintain contract tests for every
   backend status, legacy tuple mapping, `VALID_EMPTY`, partial output, and
   error-code propagation. Record affected public API/CLI/UI consumers.
2. **Convert vertically, not by global type edit.** For one capability at a
   time, change its backend/capability handler to return named contracts; keep
   the adapter at its input edge. Verify the same capability through
   `KnowledgeTool`, `EvidenceMerge`, and response serialization.
3. **Enable structured command results in QA.** Check redaction, separate
   streams, command IDs, and failure propagation. Roll back only the
   `structured_command_result` flag if this layer regresses.
4. **Enable canonical Facts in QA.** Compare fact completeness/validity and
   deterministic responders with the legacy raw-data route. Do not cache
   failed/partial facts. Roll back only `canonical_facts` if normalizers or
   reconciliation regress.
5. **Enable composite rules, then claim guard.** Evaluate precision/recall and
   grounding false positives on the stage-level golden suite. Use the
   independent flags to isolate either layer.
6. **Promote after gates.** Make the QA-enabled configuration the deployment
   configuration only after the relevant regression/acceptance gate passes.
   Keep the adapters for the documented migration window.
7. **Remove deliberately.** First remove all production callers, then turn
   adapter warning assertions into absence checks, remove the adapter, and
   delete the corresponding temporary flag in a separately reviewed task.

## Feature-flag controls

The optional `config/feature_flags.yaml` starts with migration defaults (all
off); `ORION_FEATURE_FLAGS_FILE` can point to a deployment-specific file and
the per-flag environment variables override it.

```yaml
schema_version: rollout.v1
structured_command_result: false
canonical_facts: false
composite_rules: false
claim_guard: false
```

The environment variables are:

- `ORION_FEATURE_STRUCTURED_COMMAND_RESULT`
- `ORION_FEATURE_CANONICAL_FACTS`
- `ORION_FEATURE_COMPOSITE_RULES`
- `ORION_FEATURE_CLAIM_GUARD`

They accept `true`/`false`, `1`/`0`, `yes`/`no`, or `on`/`off`. An unknown flag
or invalid value fails configuration validation rather than silently changing
rollout state. `claim_guard` affects evidence-grounding/numeric/language
validation only; the action-claim guard remains mandatory.

## Rollback and exit criteria

Rollback a failing layer by setting only its flag to `false`, restarting the
runtime, and retaining the trace/config identity with the incident. Do not
change external data schemas, manually edit result payloads, or disable the
read-only inspector chain as a rollback method.

Remove a compatibility adapter/flag only when all of the following hold:

- a repository search finds no production legacy caller;
- its adapter-specific deprecation test is replaced with an absence test;
- stage-level, contract, and end-to-end regression gates pass with the feature
  enabled;
- operator documentation and configuration examples are updated; and
- a named follow-up task records the adapter/flag removal.

## Verification

- `tests/shared/execution/test_command_result.py`
- `tests/tool/test_capability_result.py`
- `tests/model/test_feature_flags.py`
- `tests/pipeline/test_evidence_package_facts.py`
- `tests/pipeline/test_composite_rules.py`
- `tests/model/test_assessment_guard.py`
