# R08 implementation contract

This defines the R08 implementation boundary. Current checks and remaining
native/artifact gates are recorded in STATE.json and R08 session evidence.

Use the paired outbound worker transport for R08. A configured SSH transport is
R09. The control plane never implicitly executes a command locally. Add an
explicit worker command capability, disabled by default and independent of file
roots or application aliases. Report actual available PowerShell/cmd/sh/bash
executables; never silently substitute shells. Do not add a read-only classifier.

Create the server command handle in SQLite before dispatch. Persist only identity,
scope, target, shell, full normalized input hash and safe observed state metadata;
script/output stay transient. Bind handles to principal, workspace, session,
endpoint, originating request and exact target. Tools expose only the canonical
system.command.run/status/cancel names. Generic endpoint tools/API must not bypass
the command service or create unowned handles.

Worker run starts a managed process and returns a handle. Status reads bounded
current output without launching anything; cancel addresses that owned handle,
never an arbitrary PID. The independent worker ceiling rejects run/cancel when
command execution is disabled. Track commands only for the authenticated worker
connection lifetime. Disconnect/restart cancels owned processes best-effort and
marks unverified outcomes unknown; reconnect never relaunches an old command.
Server records survive restart only as metadata and recover to outcome_unknown.

Capture stdout/stderr concurrently under one combined byte limit. Continue draining
after the limit so a full pipe cannot deadlock the command. Declare UTF-8 decoding
with replacement and exact omitted-byte counts; preserve Unicode incrementally.
Use private temporary script files where shell command-line limits require them,
remove only those owned files, and never include script text in ordinary logging.
The private per-account cache records owner, exact script name, PID and creation
time before script bytes are written. On the next initialization only validated
orphans are pruned; links, altered markers and command-created files are preserved.
A crash can retain a private script until that next initialization. Windows ACLs
are read back before writing bytes. PowerShell uses -File semantics; scripts must
explicitly propagate native child exit codes when required.

On Windows, launch suspended, assign a kill-on-close Job Object before resuming,
and query the job's active process count when claiming process-tree termination.
Failure to establish the job must abort before user script execution. On POSIX,
create a new process session/group, terminate the group and inspect tracked child
identities; report uncertainty if termination cannot be verified. These are
process lifecycle boundaries, not filesystem/network sandboxes. Native Linux
behavior still needs the real R26 runner.

Timeout, user Stop, task cancellation, worker Exit and transport disconnect all
perform bounded cleanup. A normal parent exit does not justify abandoning observed
descendants. Terminal success requires the observed exit code zero; timeout/cancel
requires verified termination, otherwise outcome_unknown. Exit zero does not prove
the requested business task succeeded.

Run and model-requested cancel use the existing mutation modes and exact-payload
confirmation. Extend the server policy's configured-target handling for the
system family without widening unrelated allowlists. Scheduler remains read_only.
Direct user Stop may cancel owned active commands without a second approval.
Command ToolResults use the existing transient endpoint-evidence projection so
scripts/output do not leak into persisted history or diagnostics.

Acceptance covers independent policy denial, exact scope/target/confirmation,
handle-before-dispatch, duplicate dispatch/no replay, cancellation before launch,
separate stream/Unicode/nonzero exit, cwd with spaces, output pressure, child-tree
timeout/Stop/disconnect and shutdown. Fixtures and native Windows runner tests
remain distinct from packaged worker/app acceptance (R25) and native Linux (R26).
