# Remote browser access

## Default local use

Run `orion`. It listens on `127.0.0.1:61888`; open
`http://127.0.0.1:61888`. No login is required. Leave the remote access
variables unset for this mode.

## Remote browser

Preferred topology:

```text
remote browser
    ↓ HTTPS
private authenticated tunnel or reverse proxy
    ↓
Orion 127.0.0.1:61888
```

Create a password hash interactively:

```sh
orion auth hash-password
```

The command prompts twice without echo and writes only the encoded Argon2id
hash to stdout. Store the hash in a protected environment/secret configuration,
not in Orion's database or the UI. Start Orion with, for example:

```sh
export ORION_REMOTE_ACCESS=1
export ORION_BIND_HOST=127.0.0.1
export ORION_PUBLIC_ORIGIN=https://orion.example.com
export ORION_AUTH_PASSWORD_HASH='<encoded hash from the command>'
orion
```

`ORION_BIND_HOST` defaults to `127.0.0.1`; the fixed port remains `61888`.
The public origin must be one exact canonical origin: scheme, host, and optional
port, without credentials, path, query, or fragment. HTTPS is required except
for an explicitly loopback-only development origin. Configure the proxy or
tunnel to serve the browser at exactly this origin and forward to Orion on
loopback. Do not enable wildcard CORS or trust arbitrary forwarded headers.
Uvicorn proxy-header trust is disabled. TLS must protect traffic across any
untrusted network.

A direct non-loopback bind, such as `ORION_BIND_HOST=192.168.1.20`, is supported
only for a trusted private network with complete Orion remote auth and an HTTPS
public origin. Do not port-forward raw Orion HTTP to the public Internet.

The browser signs in with the configured password. Orion returns an HttpOnly,
Secure, SameSite=Strict cookie for a server-side session lasting at most 12
hours. Sign out revokes the session immediately. Restarting Orion logs out all
remote browsers. Login attempts are throttled process-wide after ten failures
per minute. Mutating requests, including login and logout, need the browser
`Origin` header matching `ORION_PUBLIC_ORIGIN` exactly.

`/api/health` remains public and reports only the existing cheap status and
identity. The login bootstrap and packaged static UI are public. Chat, Project,
model configuration, documents, uploads, streams, authorization decisions,
OpenAPI, and all other application APIs require a valid session. Unknown API
paths return 404 and never receive the UI shell.

MCP administrative inspection (`GET /api/mcp/servers`) is explicitly protected in
the route inventory. It exposes bounded server IDs, transport/state and catalog
names, without URLs, arguments, environment values or headers. See [MCP v1](MCP.md).

## Endpoint trust boundaries

The authoritative inventory adds browser-authenticated endpoint administration,
file transfer and desktop lifecycle APIs; pairing-token-authenticated
`POST /api/endpoints/pair`; and device-credential-authenticated
`/api/endpoints/{endpoint_id}/worker` WebSocket. Pair/device routes never use
browser cookies as authority. Pair bootstrap denies browser Origin; worker denies
Origin/query credentials. Owner mutations retain exact Origin. See
[endpoint threat model](../architecture/ENDPOINTS.md).
