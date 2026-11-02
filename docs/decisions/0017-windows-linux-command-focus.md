# ADR 0017 — Windows/Linux command focus

## Status

Current target decision, 2026-10-29. Direct user instruction: remove integrations
such as Grafana/Zabbix and focus on Windows/Linux using commands.

## Decision

The primary operating-system interface is real command execution: PowerShell/cmd
on Windows and sh/bash on Linux. Use the same ChatRuntime/ToolRunner and a shared
`system.command.run/status/cancel` contract over paired workers or configured SSH.
See [the command contract](../architecture/SYSTEM_COMMANDS.md).

Dedicated Grafana/Zabbix adapters are removed from the target product, roadmap and
acceptance criteria. Do not create replacements for other monitoring products.
Knowledge/RAG, calculator, Internet, Project, optional MCP and the common runtime
are retained. Remote Control prioritizes Device Chat, Commands and Connection;
existing desktop/browser/files/process views are secondary conveniences.

## Supersession

This decision amends ADR 0016's baseline. It supersedes ADR 0011's dedicated
monitoring scope and prohibition on generic shell/SSH command execution, and ADR
0015's worker shell prohibition/application-alias-only limitation as the primary
OS workflow. Structured helpers can remain, but they do not replace command text.

No supersession of authentication, server-owned machine identity, conversation
permissions, worker/OS rights, temporary portability, evidence handling or
outcome_unknown/no-replay semantics is intended. read_only and scheduler execution
must not be broadened using a heuristic classification of arbitrary shell text.

## Consequences

Commands may have broad OS authority; file-tool allowlists/cwd restrictions are
not a sandbox for a shell. Explicit target capability enablement and existing
confirm/auto modes gate command execution; no per-command string allowlist or
second AI agent is required.

The inspected worker currently denies shell/interpreter application launches;
the SSH adapter uses fixed operations. The new command tools are not implemented.
Dedicated monitoring code/config/tests still exist as legacy source. This turn
updates documentation/design and the migration plan; it does not pretend to remove
executable adapters, enable shells or verify native execution.

Preserve old integration reference pages as clearly marked legacy implementation
records until the source migration removes them. No commit/push or runtime change
is performed by this decision.
