# Security Policy

## Scope

Orion is currently a **local, single-user AI agent** for project knowledge and infrastructure work.
It has optional API-key authentication for Web/API use (`ORION_API_KEY`) and is intended for trusted
local/internal deployment. It is not a hardened public multi-tenant Internet service.

The architecture separates model reasoning from execution authority. The model may propose a
registered action, but only the deterministic harness can validate and execute it.

## Core security boundary

- Natural-language text is never execution authority.
- The model does not receive API keys, passwords, SSH private keys, bearer tokens, or equivalent
  credentials.
- The model selects only registered capabilities; it does not receive arbitrary shell, HTTP,
  filesystem, database, credential-lookup, or registry-mutation authority.
- Target/source references must resolve exactly. Unknown identities are rejected rather than
  fuzzy-mapped or silently defaulted.
- READ/WRITE permission is enforced from the reviewed capability effect before execution.
- Secrets and private chain-of-thought must not appear in normal logs or public traces.

See `docs/architecture/SECURITY.md` and the accepted ADRs under `docs/decisions/`.

## SSH host-key verification

SSH host-key verification is enabled by default (`StrictHostKeyChecking=yes`). Add each target's
host key to the Orion runtime user's `~/.ssh/known_hosts` before registering it.

An operator can explicitly set `strict_host_key_checking: false` for a temporary trusted-network
exception. This weakens SSH transport authentication and is not appropriate for production or
untrusted networks.

## Credential management

Grafana and Zabbix deployment credentials are stored outside the source checkout in
`/etc/orion/tool-credentials.json`.

Never hardcode credentials in source files, tracked configuration, prompts, traces, or tests.

## Infrastructure and network exposure

The application can make outbound connections to reviewed/configured resources including:

- SSH targets from the target registry;
- Grafana;
- Zabbix;
- configured model-provider endpoints;
- public Internet search/fetch through registered Internet behavior;
- the internal Project RAG service.

The model may decide that an Internet capability is useful, but network safety remains deterministic
runtime policy. Public URL fetch retains SSRF controls such as address policy, DNS/redirect
validation, timeouts, response-size bounds, and rebinding protections implemented by the tool.

In source-development Web mode, the backend listens on `localhost:61888`. In the packaged Docker
deployment, the local reverse proxy is intended for loopback access. Put separately authenticated
TLS ingress in front of Orion before exposing it beyond the trusted host/network, and review the
deployment configuration for that environment.

## Reporting a vulnerability

Report security issues privately to the maintainers when possible. Do not publish exploitable
details before the issue has been addressed.
