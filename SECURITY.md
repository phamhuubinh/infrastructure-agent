# Security Policy

## Scope

This project is currently **local-only, single-user** infrastructure investigation tool.
It is not intended to be exposed to untrusted networks.

## Known Security Considerations

### SSH Host Key Verification
SSH host key verification is intentionally disabled (`StrictHostKeyChecking=no`) for the
current trusted-network scope. See `docs/ai/09_ARCHITECTURE_DECISIONS.md` (AD-017) for
the rationale. This must be revisited before any deployment outside a trusted internal network.

### Credential Management
- Grafana and Zabbix tokens are stored in `config/secrets.local.json` (gitignored)
- Tokens were previously hardcoded in source code — assume any previously committed
  token is compromised and rotate it on the respective server
- Never hardcode credentials in source files

### Infrastructure Exposure
The application makes outbound connections to:
- SSH targets (as configured in `targets.json`)
- Grafana API
- Zabbix API
- LLM API endpoints (as configured in `servers.json`)

It does not accept inbound connections from untrusted networks.

## Reporting a Vulnerability

If you discover a security issue, please report it by creating a GitHub issue
or contacting the maintainers directly. Do not disclose vulnerabilities publicly
until they have been addressed.
