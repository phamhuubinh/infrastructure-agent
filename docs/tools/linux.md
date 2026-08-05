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

Service collection uses bounded strategies in order: systemd, SysV, OpenRC,
process presence, then known listening ports. Process/port fallbacks are
`PARTIAL`, carry lower confidence, and never claim that a service is healthy.
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
