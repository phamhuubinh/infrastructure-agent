# 06 - Tool and Capability Design

Child Tools collect evidence deterministically. They do not reason, select
other tools, choose commands from model text, make recommendations, or call an
Assessment Model. The pipeline reaches them only through `KnowledgeTool`.

## Ownership and dispatch

Each capability belongs to exactly one Child Tool and one infrastructure
domain. The current chat-runtime domains are `LinuxTool`, `GrafanaTool`,
`ZabbixTool`, and opt-in `InternetTool`; project RAG is a separate
application flow and is not a chat Child Tool. `KnowledgeTool` is the sole
runtime dispatch entry point, while Child Tool metadata is the source of truth
for what a capability can collect.

A capability declares its operational name, evidence name, typed parameter
specifications, produced Facts, target/precondition requirements, required or
optional binaries, cost/reliability characteristics, declared alternatives,
recoverable errors, and `mutation_risk`. The read-only inspector chain rejects
unsafe capabilities/parameters before a Child Tool is called.

The command strategy is owned by the Child Tool implementation. For example,
Linux service collection chooses its reviewed systemd → SysV → OpenRC →
process → listening-port fallback sequence inside the capability. The planner
chooses a declared capability, not a shell command; the model has no command
generation or execution path.

## Required result contract

One command attempt returns a `CommandResult`:

| Field | Meaning |
| --- | --- |
| `status` | `SUCCESS`, `EMPTY_SUCCESS`, or an explicit transport/environment/command/parser failure |
| `exit_code` | Process exit status when available; never inferred from output text |
| `stdout`, `stderr` | Kept separately for diagnosis; serialized with credential redaction |
| `error_type`, `command_id`, `target`, `duration_ms` | Safe, correlatable execution metadata |

One capability returns a `CapabilityResult`:

| Status | May satisfy required evidence? | Meaning |
| --- | --- | --- |
| `VALID` | Yes | A non-empty, schema-valid observation was collected. |
| `VALID_EMPTY` | Yes | The collection succeeded and the observed domain is empty. |
| `PARTIAL` | No | Some inspectable data exists, but the evidence contract is incomplete. |
| `COLLECTION_FAILED` | No | Collection did not yield valid evidence. |
| `UNSUPPORTED` | No | Target/environment cannot support this capability/strategy. |
| `INVALID_PARAMETERS` | No | Inputs were absent, invalid, or blocked before execution. |
| `PARSE_FAILED` | No | A command/source response was received but cannot satisfy the schema. |

Every non-success result carries `CapabilityError` with a stable code,
category (`transport`, `environment`, `command`, `parameter`, `parser`,
`source_api`, or `internal`), recoverability, and optional command ID. Code
uses these fields for retry/recovery; it must not parse a human-readable error
message.

## Validity, normalization, and provenance

Child Tools return normalized operational data and preserve their
`CommandResult` records; they do not create recommendations. `EvidenceMerge`
then produces an `EvidencePackage`, with the raw payload kept separately from
canonical Facts. Fact normalizers attach source, target, times, parameters,
command IDs, schema version, and confidence as `Provenance`.

Do not fabricate defaults after a failed collection. In particular:

- `0` is valid only when it was actually observed in a `VALID` Fact.
- An empty list/object is valid only with `VALID_EMPTY`, not after a failed
  command or API request.
- `PARTIAL` output may be displayed as partial context but cannot satisfy a
  required Fact/evidence requirement.
- Unsupported binaries and environments report `UNSUPPORTED`; they are not
  substituted with an unrelated command or a healthy result.

## Preconditions and recovery

Target preflight determines reachability, OS/init capabilities, privilege,
procfs/sysfs availability, and binary support before dispatch. A target-wide
transport failure stops dependent remote attempts. Optional dependencies do
not make the whole investigation fail: the affected capability returns the
appropriate structured status and remaining independent evidence can run.

Bounded recovery is limited to the alternatives declared by the failed
capability. It requires a declared recoverable error, is capped at depth two,
shares the execution budget, and records its attempts. Child Tools may use
their own reviewed internal fallback sequence, but may never accept an
arbitrary command from a caller or a model.

## Implementation rules

- Validate all typed parameters before external access. Unknown parameters and
  unsafe values fail closed.
- Prefer explicit units such as `*_bytes`, `*_seconds`, and `*_percent`.
- Keep filesystem capacity, inode pressure, cumulative I/O, and disk-health
  observations separate; one does not imply another.
- Run independent capabilities in parallel only through the execution DAG;
  keep a capability's own requests bounded and deterministic.
- Keep tools stateless. Caches are request-scoped or policy-controlled and
  never replace live evidence with a stale success.
- Return `CapabilityResult` directly in new handlers. Direct use of the
  legacy raw-payload adapter and tuple unpacking `CommandResult` is deprecated
  and emits a warning during the compatibility window.

## Related documents

- `05_EXECUTION_PIPELINE.md` — how results become evidence and assessment.
- `docs/tools/linux.md` — Linux capability and target semantics.
- `docs/migrations/deterministic_reasoning_v1.md` — adapter migration plan.
