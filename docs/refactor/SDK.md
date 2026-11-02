# Shared owner SDK

The backend is authoritative. `backend/scripts/openapi.py --write` regenerates
`ui/openapi.json`; `backend/scripts/sdk.py --write` derives the dependency-free
`ui/src/lib/sdk/generated.ts`. Both commands without `--write` check drift.
Generation rejects missing/external schema references, duplicate operation IDs
and unclassified access. Worker operations are excluded from the owner client.
The artifact records the canonical schema SHA256, typed operation inputs/outputs,
request media, response kind, required headers and the admission retry marker.
Server validation remains authoritative; TypeScript types are not runtime input
or response validation.

`OrionClient` accepts a canonical HTTPS origin or literal loopback HTTP origin.
Browser mode uses same-origin cookies. Native mode requires an injected native
HTTP bridge and an asynchronous OS secure-token-store adapter keyed by origin;
there is no browser-storage token fallback. The host owns exactly one instance
per active server profile and cancels observers/clears profile state on switches.
The R15–R17 native adapters and their artifact verification remain separate work.
An originless native bridge handles enrollment/refresh; a browser WebView fetch
must not bypass the existing Origin policy by adding wildcard CORS.

Enrollment, refresh and logout have dedicated methods. Owner administration may
create enrollment codes, list families and revoke a selected family using typed
operations. Opaque access/refresh responses are validated before vault writes.
Concurrent refused owner requests share one refresh; a later refusal reuses a
newer access token rather than replaying an old refresh credential. Refresh has
no transport retry: a lost rotation response clears local credentials and requires
enrollment. Logout invalidates in-flight retry generations; serialized vault writes
prevent a late refresh from restoring a cleared credential.

Only a401 carrying `X-Orion-Auth-Expired: 1` authorizes refresh plus retry, because
the outer bearer boundary refused that request before dispatch. An ordinary401,
network error, tool failure or server response cannot trigger mutation replay.
Only durable chat admission and its nonce-bound cancellation have one network
retry with the exact serialized body, session and client UUID. Other mutations
have no network retry. Errors expose
bounded categories/status rather than upstream bodies, credentials or internal
URLs. Redirects are refused; callers cannot override Authorization/Cookie/Origin
or Host through operation headers.

Binary uploads use Blob; binary downloads, NDJSON and SSE return byte streams.
JSON responses are capped at8MiB. `serverEvents` incrementally decodes UTF8 and
CR/LF/CRLF, comments, IDs and multiline data, bounds event buffering and cancels
the reader when the observer disconnects. An incomplete EOF event is discarded.
Consumers retain the request UUID/event UUID and reconnect GET observation with
`after` or `Last-Event-ID`; they do not resubmit chat on stream EOF. Cursor IDs are
resolved within the request, remain valid after SQLite VACUUM and conflict with
an incompatible query/header cursor. Native-family revocation and browser-session
expiry end observation without re-admitting work.

R12 adds version/doctor/target discovery, scope-owned command list/status/cancel
and skill package/preference APIs alongside existing chat/projects/documents/
profiles/MCP/jobs. Doctor reports configuration only, without model calls or
target probes. Target discovery omits SSH aliases, host paths and credentials.
Command creation continues through the canonical authorized tool/runtime path;
HTTP observation cannot execute arbitrary shell or bypass exact-payload approval.
Skill uploads accept bounded ZIP bytes with a root SKILL.md, never a server path;
no archive extraction or scripts run, and development/Graphify packages are denied
by the product parser.

R13 migrates shared UI consumers to this contract. The compatibility apiFetch
adapter resolves generated operation descriptors; newer resource/request flows
call typed operations directly. Profile/authentication context changes abort
legacy JSON bodies and streams, dispose retry generations and reject stale
results. Browser profiles navigate to the selected origin; native hosts inject
their bridge/vault rather than storing tokens in browser storage.

An immutable transient intent retains its UUID/content/session while admission
is uncertain. Known request recovery observes by GET. Cancellation reserves a
terminal cancelled nonce if admission never arrived, so delayed admission cannot
execute it. Active Stop polls canonical terminal status; completion winning the
race remains completed. Intent cleanup verifies both origin and authentication
context identity before contacting a server.

See R13_SESSION_2026-11-01.md and R13_CLOSURE_2026-11-02.json for source, bundle
and desktop/mobile-browser fixtures. These do not establish actual native vault,
CLI/mobile artifact, remote TLS or background/keyboard acceptance.
