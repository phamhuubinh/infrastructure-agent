# Endpoint runtime, persistence and threat model

See [ADR 0015](../decisions/0015-paired-endpoint-execution.md) and
[operations](../operations/ENDPOINTS.md). Composition creates EndpointStore and
EndpointManager, registers endpoint ToolDefinitions if enabled, freezes the
canonical registry, then exposes HTTP/worker WebSocket routes. ToolRunner attaches
normal RuntimeScope; only operation and closed arguments cross the device channel.
The model sees endpoint discovery refs, never credentials or transport authority.

Wire v1 uses closed discriminated hello/welcome/request/result/cancel/ping/pong
messages. Hello negotiates version/platform/worker version/capabilities/display
geometry; capability names must be from the fixed catalog. Every JSON message has
byte/depth/count bounds. Request IDs are server random UUIDs, not worker authority.
Worker rejects duplicate IDs within a bounded connection lifetime. Compression is
disabled by Orion's production uvicorn configuration and worker client. Device
connections deny Origin, query credentials and browser-cookie authentication.
One connection per device; authentication rechecks durable revocation; heartbeat
and shutdown close peers. Reads are bounded to three worker slots, mutations use
one lock and server admission is four including queued mutations. Browser access
is serialized separately. Frame production waits for the consumer and never queues
unbounded frames. Disconnect drops RPC state and manual controllers; reconnect
accepts only new requests. No automatic retry of any dispatched operation.

SQLite tables are additive: `endpoint_identities` (opaque ID, name, digest,
created/paired/last-seen/revoked times, platform/version/capabilities, safe category),
`endpoint_pairing_tokens` (digest/expiry/created/consumed) and `endpoint_audit`
(payload-free bounded lifecycle history). Active sockets, futures, browser handles,
transfer staging and desktop sessions are process-local. Restart does not infer
online status from persisted metadata. Pairing uses the SQLite transaction/lock
and conditional consume; ten failures/minute and at most sixteen token records,
256 endpoint records. Credentials use SHA-256 digest and constant-time comparison.

| Threat | Boundary / behavior |
| --- | --- |
| Stolen pairing token | Five-minute expiry, one-use atomic consume, owner-issued and bounded; revoke unexpected enrollment. |
| Stolen device credential | TLS, protected local storage, digest-only server persistence, exact endpoint binding; explicit revoke closes/rejects reconnect. |
| Compromised worker | Closed protocol, fixed capabilities, bounded untrusted result data; no registry/model/scope authority accepted. Observations may still be false. |
| Malicious webpage | Isolated profile and untrusted snapshots; no JS RPC, normal mutation authorization, downloads denied and popups bounded. |
| Traversal/symlink escape | Absolute canonical root ceiling; traversal/ADS/device namespaces denied, final publication revalidated. Protect roots/config against other local writers. |
| Replayed mutation | Random correlation, worker connection replay window; single execution, no automatic mutation retries. |
| Disconnect after mutation | `outcome_unknown` retained through ToolResult/runtime; reconnect never claims success or repeats work. |
| Stale desktop input | Ephemeral session, exclusive controller, monotonic sequence, bounded queue age; disconnect invalidates session and requires explicit reopening. |
| Browser session takeover | Existing owner cookie/TLS/exact Origin protections; manual control session binds the current cookie, expiry checked throughout streaming. Logout/expiry ends subsequent work. |

Endpoint confirmations/audits show only operation/ref, never content/form values.
Endpoint arguments are scrubbed from persistent model-call history. Successful
endpoint results are bounded transient evidence in the current Chat request;
SQLite retains a payload-omitted marker. Direct transfer/desktop routes retain no
payload data. Browser content, clipboard and images never become system instructions.

HTTP route classification lives in `orion.api.endpoints`: owner APIs,
pairing-token bootstrap and device WebSocket categories augment Remote Access's
public health/login and browser APIs. Inventory tests reject unclassified routes.
Unknown API routes remain 404. Pairing/bootstrap secrets do not appear in OpenAPI
examples. Manual uploads stage at the endpoint; browser/server/model memory never
buffers an unbounded file. Chunk ordering/offset/size is checked and final publish
uses atomic replace or no-overwrite link; failed/cancelled staging is cleaned on
abort/disconnect, with bounded stale-stage cleanup before subsequent transfers.
