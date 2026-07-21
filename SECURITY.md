# Security Policy

## Scope

This project is currently **local, single-user** infrastructure investigation tool.
Has optional API key auth for `--web` mode (see `ORION_API_KEY` env var).
Intended for trusted internal networks — not hardened for public internet exposure.

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
- External URLs via `InternetTool` (SSRF-protected, opt-in per request)
- RAG service (`RAGTool` microservice)

In `--web` mode, the backend listens on `localhost:61888` only. In Docker Compose deployment, nginx reverse proxy terminates HTTPS with self-signed certs. Optional API key auth (`ORION_API_KEY`) protects API endpoints.

## Reporting a Vulnerability

If you discover a security issue, please report it by creating a GitHub issue
or contacting the maintainers directly. Do not disclose vulnerabilities publicly
until they have been addressed.
