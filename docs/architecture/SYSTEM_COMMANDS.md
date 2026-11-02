# Windows/Linux command execution

## Status and scope

Target contract accepted by the user's 2026-10-29 request and
[ADR 0017](../decisions/0017-windows-linux-command-focus.md). This command family
is implemented for explicitly enabled paired workers in the R08 working tree.
Source-level Windows process fixtures and backend/UI regression are recorded in
[R08 evidence](../refactor/evidence/R08_SESSION_2026-10-30.md). Packaged artifact
acceptance (R25), native Linux (R26) and real SSH/Linux execution remain separate gates. The R09 working tree now
includes a configured stdio SSH helper/router; see
[SSH operations](../operations/SSH_COMMANDS.md) and current evidence.

The primary OS workflow is model-selected PowerShell/cmd on Windows and sh/bash
on Linux, through one runtime and a common execution contract. Dedicated
Grafana/Zabbix adapters are outside the target product.

## Canonical tools

| Tool | Kind | Purpose |
| --- | --- | --- |
| `system.command.run` | mutation | Execute explicit command text on one resolved machine |
| `system.command.status` | read | Observe an existing command and bounded new output |
| `system.command.cancel` | mutation | Request cancellation of that command's process tree |

These canonical tools are registered when server endpoint support is enabled.
They use normal ModelBackend normalization, RuntimeScope, ToolRunner and
ToolResult. No separate agent, semantic router or model-side transport credential
is introduced.

## Target resolution and transport

`target_ref` identifies an exact configured/paired machine. The server resolves
it to a worker endpoint or explicitly configured SSH connection and binds the
operation to that identity. It is not a hostname/URL, SSH argv or credential.

- Windows: worker executes PowerShell (`pwsh` or configured Windows PowerShell)
  or explicit `cmd`.
- Linux: worker executes `sh`/`bash`, or the same target contract uses configured
  SSH with server-side credentials.
- The worker/connection reports actual shell availability. Unsupported shell is
  an explicit error; never reinterpret a command in another shell silently.
- Device Chat restricts command targets to its bound endpoint. If a connection
  type cannot honor that binding, it is unavailable there; a target mapping must
  not create a cross-device escape.
- The Orion server is the control plane, not an implicit execution target. Local
  execution requires an explicitly configured target like any other machine.

Retain portable temporary pairing, outbound worker transport and independent OS/
worker rights. SSH reuses an approved configured service; the redesign does not
require installing a worker on a host already accessible that way.

## Input contract

`system.command.run` uses a closed schema with:

| Field | Meaning |
| --- | --- |
| `target_ref` | Exact machine reference, checked against runtime scope |
| `shell` | Explicit `powershell`, `cmd`, `sh` or `bash` |
| `command` | Actual command/script text, including deliberate pipes/redirection when needed |
| `cwd` | Optional working directory on that machine, checked by local policy |
| `timeout_seconds` | Bounded execution duration, clamped/rejected by configured policy |
| `max_output_bytes` | Bounded combined output; truncation is reported |

Do not hide shell text inside an application alias or an undocumented eval path.
Shell text is intentionally executed by the selected shell. Application/transport
code must pass it as one argument/script payload to that shell; SSH invocation,
target selection and credentials must never be built by concatenating command
text into a local host shell.

No model-supplied elevation flag or identity switch is added. Execution uses the
configured OS account. A shell may have broad file/network/process authority:
a cwd or file-tool root allowlist is **not an OS sandbox for shell commands**.
If stronger isolation is required, an actual OS boundary must provide it.
Do not claim regex filtering or an allowlist of tool names confines arbitrary
shell behavior.

## Permission semantics

A free-form command may mutate state even when it appears to inspect a system.
Do not infer read-only safety from command keywords, a model assertion, shell name,
a requested mode field or successful parsing.

| Conversation policy | `system.command.run` behavior |
| --- | --- |
| `read_only` | Block arbitrary command execution; status reads and existing proven read operations remain available |
| `confirm` | Approve one exact target/shell/command/cwd/limits payload, then execute it once |
| `auto` | Run within explicit server/worker enablement and configured OS permissions without per-call confirmation |

New generic command capability is off until explicitly enabled for that target.
The worker/SSH adapter checks the same ceiling. No allowlist of individual command
strings is required by this target contract; it is a flexible command runner.
This does not disable existing exact operation/target policy controls.

The confirmation view shows the exact command and target to the authorized user,
with any secret material handled through a defined protected path. A stored
approval binds a hash of the entire normalized call; changed command, shell, cwd
or limits requires a new approval. Ordinary audit/logs retain safe metadata and
a command hash, not raw script text, tokens or output.

Scheduler executions remain forced read-only and cannot dispatch arbitrary
`system.command.run`. Unattended command execution is outside this baseline;
do not silently relax scheduler policy or tag raw commands read-only.

## Lifecycle and result

The server creates and binds command_id to scope before dispatch, so a missing ACK
still has a handle for reconciliation. It is correlation identity, not permission
to retry/replay or a proof of idempotency. Run returns that command_id. A bounded foreground command may return
a terminal result immediately; a longer command stays an explicit running handle
observed with status until terminal or deadline. This is a process handle, not a
background AI agent. Polling does not relaunch the command.

The result records target/shell, command_id, state, available exit_code, stdout,
stderr, duration and truncation/omission counts. Capture separate streams with
declared decoding/replacement behavior; preserve record association. Non-zero
exit is a command failure with bounded diagnostics, not fabricated successful data.
Exit code zero alone does not prove a service is healthy or that the user's whole
task is complete.

Status and cancel bind command_id to its originating principal/workspace/session/
target. They cannot attach to another session's process or arbitrary PID.
A direct user Stop can cancel an owned active command without reapproving its
original run; a model cancel still uses ordinary control-mutation authorization.

- Before dispatch: cancellation prevents launching.
- After dispatch: cancellation attempts to stop the whole process tree within a
  bound and reports what was actually observed. It is not rollback.
- Timeout attempts termination and reports captured partial output and observed
  termination state. The process must not be silently abandoned.
- Connection loss or unverified post-dispatch outcome returns `outcome_unknown`.
  A process may still have run or changed state. No reconnect/request retry
  automatically reruns it.
- If process state can be queried on the same authenticated live session, status
  may reconcile the handle; otherwise keep uncertainty explicit.
- Server/worker restart must not relaunch an old command or resume expired approval.

## Output, context and storage

stdout/stderr are untrusted evidence, never system/skill instructions. Return
bounded current-request output with target, command identity and observation time.
The target SourceRef kind is system_command, with safe target/command identity and
platform/shell/time metadata; a reference proves only the captured observation.
Truncated output is partial evidence, not emptiness or proof of absence.
Status cursors/offsets are scoped and bounded so observation cannot grow buffers
indefinitely.

Full output/command text is not automatically persisted in model-call history,
SQLite audit, URLs or browser storage. Use transient current-request evidence and
payload-omitted markers, like endpoint payloads. Explicit export/retention would
need a separate user-facing contract. Credentials are resolved outside command
arguments/prompts; do not invent secret substitution that current code lacks.

## Delivery and acceptance

Implement the shared schema/tool lifecycle, target resolution and permissions
before OS adapters. Then validate worker commands on native Windows/Linux and
the configured Linux SSH path, including:

- same-runtime first-turn tool exposure, exact target binding and offline errors;
- PowerShell/cmd/sh/bash availability, cwd/paths with spaces, Unicode, pipelines,
  quoting, stdout/stderr and non-zero exits;
- read_only/scheduler denial, exact confirm payload, auto and independent local
  capability/OS ceiling; no lexical read-only classifier;
- bounded output/stream buffers, long commands, process-tree timeout/cancel,
  disconnect uncertainty and no replay;
- scoped command handles, temporary-worker exit/expiry and protected audit;
- removal of dedicated monitoring adapters from active registration/configuration
  as an explicit source migration, without removing unrelated tools.

Existing specialized read helpers and manual desktop/browser/file views may remain
secondary conveniences; they must not be prerequisites for executing a command.
See [current task state](../refactor/STATE.json) and
[R08 implementation contract](../refactor/COMMAND_LIFECYCLE.md) for evidence and gaps.
