# Security and Secret Boundary

## Protected data

The model never receives credentials. System/developer prompts, hidden policies/internal instructions, credentials/secrets, and private hidden reasoning are protected internal information.

Requests to reveal/reproduce protected internal instructions terminate as `REFUSE`; do not DISCOVER/ACTION to retrieve them. This is language-independent policy, not a keyword semantic router. See ADR-0009.

## Stage/disclosure safety

Provider output remains untrusted. Validate active decision kind, actual disclosure state, exact capability/target/source, arguments, permission/approval/budget before execution.

## Network safety

Internet/remote tools retain deterministic IP/DNS/redirect/timeout/size/credential scoping controls.

The root Compose keeps RAG internal. The standalone RAG development stack currently exposes a broader unauthenticated surface and request-controlled model endpoint boundary; harden it before untrusted-network exposure.

## Logs/metrics

Never log secrets/protected instructions/private reasoning. Operational health/metrics must reflect real state rather than hardcoded availability or permanently zero counters.
