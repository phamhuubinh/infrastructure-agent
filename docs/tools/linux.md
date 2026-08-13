# Linux Tool

> Read-only Linux evidence from the Orion runtime or registered SSH targets.

## Overview

The Linux Tool uses `LocalExecutionBackend` for `localhost` and
`SSHExecutionBackend` for registered remote targets. It is dispatched only
through `KnowledgeTool`.

## Capabilities

The registered operational capabilities are:

- System and performance: `get_system`, `get_cpu`, `get_cpu_usage`,
  `get_system_load`, `get_memory`, `get_swap`, `get_uptime`, `get_boot_time`,
  `get_time`, `get_time_sync`, `get_locale`, and `get_environment`.
- Storage: `get_disk`, `get_disk_usage`, `get_filesystem`,
  `get_filesystem_health`, `get_filesystem_inode`, `get_disk_io`,
  `get_block_device`, and `get_disk_device_health`.
- Network: `get_network`, `get_dns`, `get_listening_ports`,
  `get_interface_stats`, `get_bandwidth`, and `get_ping_latency`.
- Services and processes: `get_services`, `search_service`, `get_service`,
  `get_service_logs`, `get_process`, `search_process`, and
  `get_process_by_name`.
- Inventory and containers: `get_user`, `get_session`, `get_recent_logins`,
  `get_package`, `search_package`, `get_hardware`, `get_pci`, `get_usb`,
  `get_gpu`, `get_module`, `get_docker`, and `get_lxd`.
- Security and logs: `get_ssh`, `get_secureboot`, `get_apparmor`,
  `get_selinux`, `get_firewall`, `get_certificate`, `get_journal`, and
  `get_log`.

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
  "assessment": "...",
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
          "success": true
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
result = tool.execute({"action": "get_cpu_usage"})
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
      "strict_host_key_checking": true
    }
  }
}
```

Host key verification is enabled by default. Record the target's verified host key in the
Orion runtime user's `~/.ssh/known_hosts` before first use. Set
`strict_host_key_checking` to `false` only as an explicit, temporary exception on a trusted
network; that mode disables host identity verification.

## Caching

Repeated `/proc` filesystem reads are cached within a single request to reduce I/O overhead. The cache is per-request and does not persist across investigations.
