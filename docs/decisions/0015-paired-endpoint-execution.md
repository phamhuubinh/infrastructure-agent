# ADR 0015 — Paired endpoint execution

## Status

Accepted; implements Remote Endpoint v1 (#162).

## Decision

Orion remains the single control plane, model and ChatRuntime. Windows/Linux workers
are model-free capability executors. They initiate one authenticated outbound
WebSocket through Orion HTTP; they expose no listener. A stable `endpoint.*`
ToolDefinition family enters the canonical registry before freeze when
`ORION_ENDPOINTS=1`. Pairing, online state and revocation never change schemas.
RuntimeScope stays on Orion. Workers neither choose identity/scope/mutation mode
nor publish registry definitions or prompts. Endpoint results are untrusted data.

An owner issues a random five-minute one-use pairing token. SQLite retains only
SHA-256 digests, atomically consumes the token and issues a random per-device
credential once. The worker retains that credential in protected local state.
Browser cookies and device credentials authenticate separate routes. TLS is
required outside explicit loopback development. Re-pairing requires owner action;
revocation invalidates reconnect and closes the current channel.

The worker's strict local policy is an independent ceiling. Host reads are enabled;
files, process mutation, clipboard, isolated browser, capture and input require
explicit local configuration. Read/write roots are separate, canonicalized and
checked again before staged atomic publication. No shell, eval or arbitrary JS RPC
exists. Models use normal ToolRunner validation, conversation mutation modes and
exact-call confirmations; scheduler executions remain forced read-only.

From the dispatch send attempt onward, interruption of an unverified mutation is
`outcome_unknown`. Neither side replays operations on reconnect. Server-generated
correlation IDs, a bounded replay window, per-device mutation serialization and
bounded read/queue admission control operation lifecycle. Manual desktop control
is an authenticated owner action with a separate ephemeral session, exclusive
controller, monotonic input sequence and payload-free lifecycle audit. Stale
queued desktop events are rejected; disconnect invalidates control sessions.

Browser automation uses one isolated Playwright Chromium context, never the user's
profile. Provisioning is explicit. Downloads are denied in v1. Windows desktop
capture/input uses MSS and pynput's native APIs with secure-desktop denial. Linux
supports X11; Wayland/headless environments fail closed. No UAC/portal privilege
bypass is added. Frames are bounded JPEGs and are never persisted by transport.
Endpoint tool payloads are transient current-request evidence, omitted from SQLite
history and scrubbed from mutation confirmations. Desktop stream/UI payloads stay
in memory; no URL or browser storage carries them.

## Consequences

Workers need Python 3.12+ and executor dependencies, but no Orion server, model,
embeddings, UI or npm. A separate wheel and two install archives share Orion's
version/source SHA. Full server releases remain independently installable. Local
policy is not an OS sandbox: an owner must protect worker configuration and roots
from other local writers. A compromised paired worker may falsify observations;
server policy can limit operations but cannot make a compromised host trustworthy.
