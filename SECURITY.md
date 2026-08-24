# Security Policy

## Scope

Orion is a local, single-user agent intended for trusted local/internal deployment, not a hardened public multi-tenant service.

## Core boundary

- Natural-language text is never execution authority.
- The model never receives credentials/secrets.
- System prompts, developer prompts, hidden policies/internal instructions, credentials/secrets, and private hidden reasoning are protected internal information.
- Requests to reveal/reproduce protected internal instructions terminate as `REFUSE`; Orion must not use discovery/actions to retrieve them.
- Parsed model decisions remain untrusted until active-stage/disclosure/exact-authority validation passes.
- Unknown/malformed target/source/capability/configuration fails closed; no fuzzy/default-localhost behavior.
- READ/WRITE comes from reviewed capability effect.
- Objective final execution claims must agree with structured observations.

## SSH/credentials

SSH host-key checking is enabled by default. Deployment credentials live outside the checkout, normally `/etc/orion/tool-credentials.json`.

## Network exposure

The root packaged Compose stack is intended for loopback-local access and keeps RAG internal.

### Standalone RAG development stack

`src/tool/RAGTool/docker-compose.yml` currently publishes RAG/Qdrant and is not equivalent to the root deployment. It also accepts request-scoped model endpoint configuration in analysis requests. Until hardened, do not expose it to an untrusted network.

The target is loopback-only development exposure or explicit auth/mTLS, secured vector administration, and server-side SSRF/DNS/redirect/private-address protection without arbitrary bearer-token forwarding.

See `docs/development/IMPLEMENTATION_GAPS.md`.
