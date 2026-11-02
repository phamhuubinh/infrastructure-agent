# R12 native owner access and resumable admission

Implementation work follows the existing single local owner/workspace; native
tokens do not invent another principal or allow a caller to choose RuntimeScope.
Browser access keeps its cookie and exact-Origin boundary. Native owner bearer
access is separate from endpoint pairing/worker tokens and provider credentials.
No CORS wildcard, provider key in clients, or model-authored permission is added.

An authenticated owner creates a short-lived, single-use random enrollment code.
A native client exchanges that code plus bounded display/platform metadata for
opaque access/refresh tokens. Persist only SHA256 digests, fixed lifetimes and
revocation/rotation metadata in the protected managed database. Access is short
lived; refresh rotates atomically, detects recognized token replay and revokes
that family. Invalid random tokens cannot revoke a known family. A family has an
absolute expiry and bounded rotation history. Logout/revoke prevents subsequent
requests; an already admitted operation still has ordinary runtime Stop/deadline
semantics. Tokens never enter model context, event/diagnostic payloads or URLs.
Native client secret storage is an OS secure-storage responsibility in R15–R17.

Public enrollment/refresh endpoints accept explicit JSON secrets, not ambient
owner cookies. Only validated native bearer access may bypass browser Origin
checks on protected owner API routes. Unknown/expired/revoked bearer credentials
fail closed without cookie fallback. Worker/pairing boundaries remain distinct.
Remote deployment retains the existing HTTPS/public-origin requirements.

Managed restore into a new data directory must revoke copied native sessions and
enrollment codes, so a backup cannot resurrect old client sessions. Ordinary
restart preserves still-valid sessions; refresh replay is never resolved by
re-enabling an old credential. Existing content/skills/provider backup data stays
intact and original bundles remain immutable.

Add durable request admission keyed by a client-generated UUID and actual owner/
workspace/session/content identity. Repeated identical admission returns the same
server request; changed content/scope conflicts. Restart must not replay a lost
mutation: interrupted requests retain the R07 recovery outcome. The application
owns admitted background tasks and shutdown/Stop; SSE or event polling observes
the existing request and never enqueues another model turn merely to reconnect.
The shared typed SDK may retry only this idempotent admission with the same key;
arbitrary POST/tool mutations get no blind transport retry.

This is the implementation contract, not a completion claim. Required fixtures:
single-use/expiry/hash-only storage/atomic rotation/replay/revoke/restart/restore,
browser/native/worker boundary and scope denial, duplicate admission versus content
conflict, disconnected/resumed observation, failed shutdown and canonical model/
command no replay. Generate shared schemas/client types from the authoritative API
and validate browser/native transport fixtures for R12. UI adoption, headless CLI
and actual native bridge/vault adapters are verified in R13–R17 and artifact gates.
