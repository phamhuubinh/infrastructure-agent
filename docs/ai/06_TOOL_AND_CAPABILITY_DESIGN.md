# 06 - Tool and Capability Design

Child Tools collect evidence deterministically. They do not reason, select
other tools, accept commands from model text, make recommendations, or call an
assessment model. The pipeline reaches them only through `KnowledgeTool`.

## Current domains and ownership

The chat runtime registers four domains:

- `LinuxTool` for local/SSH host evidence.
- `GrafanaTool` for dashboards, data sources, alerts, and annotations.
- `ZabbixTool` for hosts, items/history, triggers, events, templates, and
  maintenance state.
- `InternetTool` for bounded public search and fetch.

Project RAG is a separate API/UI workflow and is not a Child Tool.

Each capability belongs to one Child Tool. The Child Tool metadata is the
single source of truth for operational name, evidence name, typed parameters,
produced Facts, target/precondition requirements, required/optional binaries,
cost, reliability, alternatives, recoverable errors, and mutation risk.
`KnowledgeTool` aggregates that metadata; pipeline modules do not duplicate it.

## Dispatch and safety

`ExecutionRuntime` dispatches only through `KnowledgeTool`. The inspector chain
applies the read-only, parameter-safety, tool, and target policies before
external access. The selected Child Tool owns its reviewed collection/fallback
sequence. Neither callers nor the model can provide an arbitrary command.

Target preflight checks reachability, operating system/init support,
privilege, procfs/sysfs availability, and binaries. A target-wide transport
failure stops dependent work. Optional dependency absence produces a typed
unsupported/failure result while independent evidence continues.

## Result contracts

One backend attempt returns `CommandResult`:

| Field | Meaning |
|---|---|
| `status` | Explicit success, empty success, or transport/environment/command/parser failure |
| `exit_code` | Process exit status when available |
| `stdout`, `stderr` | Separate streams, redacted on serialization |
| `error_type`, `command_id`, `target`, `duration_ms` | Safe execution metadata |

One capability returns `CapabilityResult`:

| Status | Satisfies required evidence | Meaning |
|---|---:|---|
| `VALID` | Yes | Non-empty schema-valid observation |
| `VALID_EMPTY` | Yes | Successful observation of an empty domain |
| `PARTIAL` | No | Inspectable but incomplete data |
| `COLLECTION_FAILED` | No | No valid observation |
| `UNSUPPORTED` | No | Unsupported target, environment, or dependency |
| `INVALID_PARAMETERS` | No | Missing, invalid, or blocked input |
| `PARSE_FAILED` | No | Response cannot satisfy the expected schema |

Every non-success result contains a stable `CapabilityError` code, category,
recoverability flag, and optional command ID. Runtime policy uses these fields,
not error-message parsing.

## Validity and provenance

`EvidenceMerge` converts tool results into `EvidencePackage` records. Raw data
is separate from canonical Facts. Fact normalizers attach source, target,
times, parameters, command IDs, schema version, confidence, and provenance.

- A numeric zero is valid only when observed in valid evidence.
- An empty list/object is valid only with `VALID_EMPTY`.
- Partial evidence can be shown as partial context but cannot satisfy a
  required Fact.
- Unsupported dependencies remain `UNSUPPORTED`; they do not produce a
  substitute healthy value.

## Recovery

Recovery can use only alternatives declared in the failed capability's
metadata. It requires a declared recoverable error, is capped at depth two,
shares the execution budget, and records each attempt. Child Tool internal
fallbacks are fixed reviewed sequences.

## Engineering contract

- Validate typed parameters before external access; unknown or unsafe values
  fail closed.
- Use explicit units such as `*_bytes`, `*_seconds`, and `*_percent`.
- Keep capacity, inode pressure, cumulative I/O, and device-health facts
  separate.
- Schedule independent capabilities through the execution DAG.
- Keep Child Tools stateless; policy-controlled caches never turn stale data
  into fresh success.
- Return `CapabilityResult` at capability boundaries. The raw-payload and tuple
  adapters exist only for current backward compatibility and emit deprecation
  warnings for direct use.

## Related documents

- `05_EXECUTION_PIPELINE.md`
- `docs/tools/linux.md`
- `docs/tools/grafana.md`
- `docs/tools/zabbix.md`
- `docs/tools/internet.md`
