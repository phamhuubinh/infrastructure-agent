# R09 SSH command implementation boundary

R09 is in progress; this contract does not claim a working SSH command transport.
Keep the canonical CommandService ownership, exact approval, safe persistence and
no-replay behavior from R08. Do not retrofit arbitrary text into legacy fixed
Linux probes or revive monitoring adapters.

## Administrative target and credentials

Use an explicitly selected `ORION_SSH_COMMAND_CONFIG` JSON file, version1, with at
most16 targets. Target references have a separate `ssh:<name>` namespace, and
`commands` defaults false. Each target names an exact SSH alias and absolute
server-side SSH configuration/known-hosts paths. These are never model arguments,
model context, browser configuration, managed-data exports or public error text.
No implicit workstation SSH discovery, old monitor alias, host wildcard or model
supplied credential/identity/option fields are accepted. SSH config and its
Includes/ProxyCommand are trusted administrator configuration, not untrusted input.

SSH must run as an argv subprocess with no local shell. Require BatchMode,
StrictHostKeyChecking=yes, an explicit known-hosts file, bounded connect/keepalive
settings, no PTY, no agent/X11/port forwarding, no LocalCommand and no inherited
RemoteCommand/ControlMaster session. Never auto-accept a changed/new host key.
An installed local OpenSSH client and a configured remote account are prerequisites;
do not install services, copy private keys or modify user SSH configuration.

## Channel and remote lifecycle

The selected design is an ephemeral standard-library Python3 helper over a single
SSH stdin/stdout channel. Remote Python3.10+ is a checked prerequisite; it is not a
worker installation or AI agent. Transfer the fixed helper source in a bounded
stdin prelude; command JSON and script bytes travel only inside the authenticated
SSH channel, never in local argv or an interpolated local shell. Shell discovery
must come from the remote helper, never the control plane's PATH.

The helper must independently validate closed protocol inputs and bound active
commands, retained handles, separate drained output buffers/pages and heartbeat
lease. Preserve UTF-8 replacement/raw-byte cursor behavior. Status observes an
existing connection-owned handle; no new channel may recreate an old command.
Connection generation changes, SSH failure, missing ACK or restart preserve
uncertainty and never replay run. A status operation must not spawn a fresh command.

Remote process cleanup requires Linux process-group/session ownership and process
creation identities, plus a bounded supervisor that survives command-parent exit
long enough to kill owned descendants. EOF, heartbeat expiry, timeout, Stop and
shutdown attempt tree termination. Killing the local ssh client is not proof of
remote termination. Use outcome_unknown whenever remote cleanup is unverified.
Do not kill arbitrary PIDs supplied by a model or stale marker. Remote script cache
must be private/provenanced and prune only known artifacts, preserving unrelated
files and documenting crash retention. Output remains transient; do not add an
unbounded remote log spool.

## Current containment and composition

The implemented helper uses a per-command Linux child subreaper before shell
launch. Detached/session-changing orphan descendants remain owned by that command's
supervisor, which kills/reaps direct/adopted children through pidfds and checks
kernel ECHILD. The private metadata FD reports cleanup completion separately from
the shell exit outcome. The helper independently verifies observed process cleanup;
both observations are required before `process_tree_terminated=true`. A missing or
failed observation stays unknown, even after a later cancel retry. Source fixtures
reproduced and repaired the prior double-fork false-success case.

Compose worker and SSH transports behind the existing command-service port with
explicit capability preparation. Device Chat remains restricted to its actual
paired endpoint; an SSH target must not escape that binding. SSH target connection
material is absent from tool schemas and model summaries.

Validate strict administrative configuration, argv/quoting/option injection,
canonical modes/confirmation/scope, real wire/helper operation, output pressure,
Stop/timeout/EOF/abrupt channel loss, uncertain remote termination and no replay.
Actual private Ubuntu/QEMU SSH3/process10 source fixtures are recorded in
[R09 evidence](evidence/R09_SESSION_2026-10-31.md). They include detached descendants
on normal/timeout/Stop/EOF/crash paths. Fake stdio is not counted as that proof;
exact Linux CLI/service/worker artifact acceptance remains part of R26.

Primary references: [OpenSSH ssh(1)](https://man.openbsd.org/ssh),
[ssh_config(5)](https://man.openbsd.org/ssh_config), and
[Python subprocess sessions](https://docs.python.org/3.12/library/subprocess.html).
For descendant adoption see the Linux man-pages maintainer's
[PR_SET_CHILD_SUBREAPER](https://www.man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html).
