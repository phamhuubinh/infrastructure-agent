# Linux Tool

> Remote Linux system investigation via SSH.

## Overview

The Linux Tool connects to remote targets over SSH and executes diagnostic commands to collect system evidence. It is one of the core Child Tools dispatched by the KnowledgeTool.

## Capabilities

| Capability | Description | Evidence Name |
|------------|-------------|---------------|
| `assess_machine` | Full system health snapshot | `assess_machine` |
| `cpu` | CPU info, load, usage | `cpu` |
| `memory` | Memory and swap usage | `memory` |
| `disk` | Disk usage, filesystem health, block devices | `disk` |
| `network` | Interfaces, DNS, listening ports | `network` |
| `process` | Process list, zombie detection, process search | `process` |
| `service` | Service status, Docker, LXD containers | `service` |
| `system` | Users, hardware, PCI, USB, GPU, journal, logs, time, locale, env, sessions, modules, recent logins | `system` |
| `package` | Installed packages, package search | `package` |
| `security` | SSH config, Secure Boot, AppArmor, SELinux, firewall, certificates | `security` |

Core output uses explicit units (`*_bytes`, `*_seconds`, `*_percent`) and is
schema-validated before a capability can return `VALID`. Capacity, inode
capacity, cumulative device I/O, and physical device health are separate facts;
a filesystem usage percentage or read-only mount flag is never presented as a
SMART/NVMe health result.

## Execution and evidence contract

Linux command strategies are reviewed code owned by `LinuxTool` and its
capability modules. The planner selects a named capability such as
`get_service`; it does not compose a shell command, and an Assessment Model
cannot submit one. A capability records every backend attempt as a
`CommandResult` and returns a `CapabilityResult` through `KnowledgeTool`.

| Result | Interpretation |
| --- | --- |
| `CommandResult.SUCCESS` / `EMPTY_SUCCESS` | The command ran. An empty success is an observation, not a failure. |
| `CapabilityResult.VALID` / `VALID_EMPTY` | Only these statuses can satisfy a required evidence contract. |
| `PARTIAL` | Some fallback evidence is available but cannot establish the primary claim. |
| `COLLECTION_FAILED`, `UNSUPPORTED`, `INVALID_PARAMETERS`, `PARSE_FAILED` | Collection/validation failed explicitly; remaining independent capabilities may continue. |

Command records retain status, exit code, separate stdout/stderr, error type,
target, duration, and a command ID. Serialized diagnostics redact common
credential forms. The pipeline normalizes successful payloads into canonical
Facts with target, unit, validity, freshness, and command/source provenance.
It never converts a failed command into `0`, `{}`, `[]`, or a healthy result.

### Binaries, preflight, and fallback

Every target is preflighted before dispatch. Required binaries make an
unsupported capability explicit; optional binaries merely restrict the
reviewed strategy available for that capability. Do not install tools or
modify the target as part of an Orion investigation: the runtime is read-only.

Service collection uses bounded strategies in order: systemd, SysV, OpenRC,
process presence, then known listening ports. Process/port fallbacks are
`PARTIAL`, carry lower confidence, and never claim that a service is healthy.
The generic capability-recovery layer can try only declared alternatives for a
declared recoverable error, at most twice, within the request's shared budget.

Service log collection accepts a validated unit, bounded line limit, and time
range. It uses `journalctl -u`; file fallback is restricted to reviewed paths
and reports unsupported when it cannot honor a requested time bound.

## Usage Examples

### Via CLI

```bash
orion run
> Check CPU on webserver01
```

### Via API

```bash
curl -X POST http://localhost:61888/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Check CPU usage on webserver01"}'
```

Expected response structure:

```json
{
  "response": "...",
  "steps": [
    {
      "stage": "intent",
      "intent": "cpu_usage",
      "confidence": 0.95
    },
    {
      "stage": "evidence",
      "items": [
        {
          "evidence_name": "cpu",
          "target": "webserver01",
          "success": true,
          "data": {
            "cores": 8,
            "model": "Intel Xeon",
            "usage_percent": 45.2
          }
        }
      ]
    }
  ]
}
```

### Python

```python
from src.tool.linux import LinuxTool
from src.tool.execution_backend import SSHExecutionBackend

backend = SSHExecutionBackend(
    host="webserver01",
    user="root",
    port=22,
    identity_file="~/.ssh/id_rsa",
)
tool = LinuxTool(backend=backend)
result = tool.execute({"capability": "cpu"})
print(result.data)  # CPU diagnostic data
```

## Configuration

### Meaning of `localhost`

`localhost` always means the environment running Orion, not an implicit
physical host. In the packaged Compose deployment its display name is
`orion-api`, and Linux evidence comes from the API container namespaces. In
source CLI mode it means the local Orion process environment. To monitor the
physical Docker host or another server, register an explicit SSH target; Orion
does not mount host PID/network/filesystem namespaces behind `localhost`.

Every Linux target is preflighted before capability dispatch. The short-lived
environment fingerprint records reachability, OS, init system, privilege
level, procfs/sysfs availability, and available command strategies. An
unreachable SSH target stops after one transport probe; missing optional
binaries produce structured `UNSUPPORTED` evidence.

`localhost` is not a shortcut to the Docker host and it never silently falls
back from an explicit unknown target. If a query names a target that cannot be
resolved, Orion asks for clarification instead of collecting from localhost.
See [Troubleshooting & FAQ](../troubleshooting.md#linux-collection-failure-codes)
for the error-code-to-operator-action table.

Targets are defined in `targets.json`:

```json
{
  "targets": {
    "webserver01": {
      "backend": "ssh",
      "host": "192.168.1.10",
      "user": "root",
      "port": 22,
      "identity_file": "~/.ssh/id_rsa",
      "strict_host_key_checking": false
    }
  }
}
```

## Caching

Repeated `/proc` filesystem reads are cached within a single request to reduce I/O overhead. The cache is per-request and does not persist across investigations.
