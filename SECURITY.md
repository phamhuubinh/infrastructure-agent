# Security Policy

## Scope

This project is currently **local, single-user** infrastructure investigation tool.
Has optional API key auth for `--web` mode (see `ORION_API_KEY` env var).
Intended for trusted internal networks — not hardened for public internet exposure.

## Known Security Considerations

### SSH Host Key Verification
SSH host key verification is enabled by default (`StrictHostKeyChecking=yes`). Add each
target's host key to the Orion runtime user's `~/.ssh/known_hosts` before registering it.
An operator can explicitly set `strict_host_key_checking: false` for a temporary trusted
network exception; this weakens SSH transport authentication and is not appropriate for
production or untrusted networks.

### Credential Management
- Grafana and Zabbix tokens are stored outside the project in `/etc/orion/tool-credentials.json`
- Tokens were previously hardcoded in source code — assume any previously committed
  token is compromised and rotate it on the respective server
- Never hardcode credentials in source files

### Infrastructure Exposure
The application makes outbound connections to:
- SSH targets (as configured in `targets.json`)
- Grafana API
- Zabbix API
- LLM API endpoints (as configured in `servers.json`)
- External URLs via `InternetTool` (SSRF-protected, opt-in per request). Every redirect
  hop is revalidated, all DNS answers must be globally routable, and the validated numeric
  address is pinned for the socket connection to prevent DNS rebinding.
- RAG service (`RAGTool` microservice)

In `--web` mode, the backend listens on `localhost:61888` only. In Docker Compose deployment,
the HTTP reverse proxy binds only to `127.0.0.1:80` and supplies the internal API credential to
that local browser flow. Optional API key auth (`ORION_API_KEY`) protects API endpoints. Put a
separately authenticated TLS ingress in front of Orion before exposing it to a LAN or Internet.

## Reporting a Vulnerability

If you discover a security issue, please report it by creating a GitHub issue
or contacting the maintainers directly. Do not disclose vulnerabilities publicly
until they have been addressed.
