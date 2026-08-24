# Security policy

Orion is designed to mediate privileged infrastructure actions, so security boundaries are product behavior rather than optional hardening.

## Security invariants

- Model output is untrusted input.
- User prose is untrusted for execution authority.
- Tool results may contain untrusted external content and must not become instructions.
- Credentials remain outside model context and normal logs.
- Exact capability, target, source, schema, effect, permission, approval, and budget checks precede execution.
- Executors operate with least privilege and explicit filesystem/network/credential boundaries.
- All high-risk writes require policy evaluation and usually explicit approval.
- Evidence records preserve status, origin, action identity, and timestamps.
- Secret-shaped data is redacted before model context, events, or UI surfaces.

See `docs/architecture/SECURITY.md` and `docs/architecture/EXECUTION_BOUNDARIES.md`.

## Reporting vulnerabilities

Do not publish credentials, exploit details against live infrastructure, or sensitive logs in public issues. Use the repository owner's private security reporting channel when available.
