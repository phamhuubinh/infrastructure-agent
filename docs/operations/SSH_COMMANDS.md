# Configured Linux SSH commands

The working tree implements an SSH adapter for the canonical
`system.command.run/status/cancel` tools. Current source/fixture and native gates
are recorded in [STATE.json](../refactor/STATE.json); a source description does not
certify a released artifact, real SSH account or Linux process lifecycle.

## Explicit server configuration

Set `ORION_SSH_COMMAND_CONFIG` to an owner-managed JSON file on the Orion server.
Unset means disabled. It never imports a workstation's SSH targets, the legacy
monitor alias, or model-supplied connection parameters. `commands` defaults false.

```json
{
  "format_version": 1,
  "targets": [
    {
      "target_ref": "ssh:lab",
      "ssh_alias": "lab-linux",
      "config_file": "/home/orion/.ssh/config",
      "known_hosts_file": "/home/orion/.ssh/known_hosts",
      "commands": true
    }
  ]
}
```

Windows server paths can use `C:/Users/owner/.ssh/config` and a matching absolute
known-hosts path. Paths with spaces work. SSH aliases are exact safe names, not
host strings/options/commands. At most16 unique targets are accepted; unknown
fields, invalid versions/paths and linked or oversized configuration fail closed.
Known-hosts paths cannot contain SSH expansion tokens. Connection files are
rechecked for ordinary ownership at use. Config and its Includes/ProxyCommand
remain trusted administrator configuration; do not populate them from model input.

The local OpenSSH client must be installed. The configured account must already
authenticate non-interactively and have a verified host-key entry in the explicit
known-hosts file. Orion requires BatchMode and StrictHostKeyChecking=yes; it never
accepts an unknown/changed key or prompts for a password. Agent/X11/port forwarding,
LocalCommand, RemoteCommand, PTY and ControlMaster reuse are disabled. Host/account/
key material stays server-side; the model sees only `ssh:lab` as the target.

SSH targets work without enabling paired endpoints. Device Chat remains bound to
its actual paired endpoint and cannot switch to `ssh:lab` to escape that identity.
Server read_only/confirm/auto and exact-payload approval are unchanged. SSH account
rights apply; neither cwd nor file-tool roots provide a shell sandbox.

## Remote prerequisites and lifecycle

The target is Linux with Python3.10+ standard library, readable `/proc`, normal
Linux process groups/prctl and pidfd support for safe observed-child signaling.
The helper discovers actual `/bin` or `/usr/bin` sh/bash executables. Missing
capabilities fail explicitly; no shell substitution, pip/worker installation,
service, autostart or OS account modification is performed.

On the first authorized new run, Orion sends fixed helper source over SSH stdin,
receives actual shell capabilities, creates the owned command handle in SQLite,
then sends validated command JSON. Scripts are not concatenated into a local shell
or local SSH argv. Only the explicitly configured SSH client runs locally.

One bounded helper belongs to one live SSH generation. Status/cancel observe an
existing scoped handle and never open a replacement channel. A duplicate original
request/call does not reconnect or rerun a command. Channel loss/restart retains
`outcome_unknown` or already known terminal metadata, with output unavailable.
A fresh explicitly authorized run can establish a fresh channel.

The Linux helper uses private/provenanced script files and memory-only bounded
stdout/stderr capture. It drains extra bytes and reports omissions; status pages
use raw-byte cursors and UTF-8 replacement. At most4 commands and16 retained
observations belong to a channel; uncertain handles are retained conservatively.
An idle helper expires after25seconds without protocol traffic; the server sends
heartbeats while the channel is owned.

Each command has a new-session supervisor with a parent-death signal and an
independent timeout. It emits only observed shell-exit metadata, then kills its
own group; the helper separately checks group/observed-child cleanup. Stop, EOF,
timeout and shutdown attempt bounded cleanup. Closing a local SSH process is not
proof of remote termination. Unreadable/incomplete process observation or failed
cleanup remains `outcome_unknown`, never a fabricated successful cancellation.
Process groups are lifecycle ownership, not a defense against deliberately
escaping processes or a replacement for OS isolation.

Scripts are removed on normal cleanup. After a helper crash the next cache startup
prunes only owned artifacts whose strict helper PID/start/boot provenance is dead.
Unknown files, links and modified markers are preserved; cleanup does not recurse
or kill a PID read from a marker. Raw output is not spooled to persistent files.
OS/SSH/EDR telemetry and command-created files remain outside this artifact cleanup.

## Verification boundary

Windows fixtures validate configuration, stdio protocol, package independence,
canonical runtime/authorization and no replay. Local `ssh -G` checks only option
parsing, not a remote connection. Native Linux fixtures cover actual helper output,
timeout/cancel/EOF and abrupt parent death; they require the R26 runner. Real SSH
host-key/auth and exact packaged Linux artifacts remain separate acceptance gates.
SSH configuration/key files remain external operator material and are excluded
from the managed DB/blob/provider-credential export.
