# Tools

## Target catalog

All registered model-callable schemas are available on the first model turn in
Chat, Project and Device Chat; execution still requires valid scope/permissions.

| Family | Role |
| --- | --- |
| Knowledge/RAG | Scoped documents and exact reads |
| Calculator | Deterministic arithmetic |
| Internet | Search/fetch evidence |
| Windows/Linux commands | PowerShell/cmd/sh/bash on one exact machine (design target) |
| Scheduler | Read-only scheduled runtime requests and task management |
| Optional MCP | Configured external tools in the same registry |
| Endpoint conveniences | Existing files/process/browser/desktop capabilities |

The primary OS contract is [system.command.run/status/cancel](../architecture/SYSTEM_COMMANDS.md),
through workers or configured Linux SSH. It accepts actual command text rather
than requiring a specialized operation for every system task.
Dedicated monitoring adapters are removed from the target catalog; do not add
replacement product-specific monitoring integrations.

## Source status

The generic command family is not implemented. Existing fixed Linux operations
and endpoint aliases are current legacy implementation paths, not proof that
PowerShell/cmd/bash are accepted. Dedicated monitoring code also remains until
a source migration changes registration/configuration/tests.
See [implementation inventory](../development/IMPLEMENTATION_STATUS.md).

## Model-driven workflow

A user may ask to inspect Windows services, find Linux disk usage or fix a
configuration. The model chooses a suitable command for the actual shell and
machine, receives bounded stdout/stderr and exit/timeout state, and verifies the
relevant result. It does not need a separate AI agent or an intent router.

Raw commands are mutation-capable. read_only and scheduler cannot dispatch them;
confirm binds the exact command/target, while auto obeys explicit target capability
and OS rights. Status observations never relaunch the process.

[Endpoint conveniences](ENDPOINTS.md) and [legacy fixed Linux tools](LINUX.md) remain
implementation references. [MCP](../operations/MCP.md) and
[Scheduler](../architecture/SCHEDULER.md) retain their existing scope and policy.
