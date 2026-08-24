# Security architecture

## Threat model

Assume:

- model output can be wrong or adversarial;
- user content can request unsafe actions;
- project documents and internet/tool output can contain prompt injection;
- integrations can fail or return hostile payloads;
- executors can contain bugs;
- credentials are highly sensitive;
- operators can make approval mistakes.

## Security layers

1. **Tool exposure** — model can only propose currently exposed capabilities.
2. **Contract validation** — exact closed schemas.
3. **Authority** — exact capability + target/source relationship.
4. **Permission policy** — allow/ask/deny.
5. **Approval binding** — exact action fingerprint and expiry.
6. **Budget** — bounded autonomous work.
7. **Execution isolation** — least privilege, filesystem/network/credential boundaries.
8. **Evidence validation** — success cannot be fabricated from prose.
9. **Redaction/audit** — secrets excluded, actions traceable.

## Protected data

Never expose to the model unless explicitly designed and reviewed:

- API keys;
- passwords;
- private keys;
- bearer/session tokens;
- raw `.env` secrets;
- unrestricted database credentials;
- internal security policy secrets;
- private chain-of-thought.

## Prompt injection

External content is data. It may inform reasoning but cannot change the available tool set, authority policy, permission mode, approval state, credentials, or system instructions.

## Target/source configuration

Configuration must validate at load time. Unknown or malformed refs are errors. `localhost` is never an implicit fallback. A local target exists only when explicitly configured as a valid target.

## Write safety

High-impact actions should require explicit target display, risk/effect classification, approval, bounded credentials, post-action evidence, and audit events.

## Supply chain

Pin and audit dependencies used in privileged executor paths. Minimize subprocess parsing and shell interpolation. Prefer typed API clients or fixed command constructors.
