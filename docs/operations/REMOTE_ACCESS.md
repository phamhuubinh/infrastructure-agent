# Remote browser access

## Default local use

Run `orion`. It listens on `127.0.0.1:61888`; open
`http://127.0.0.1:61888`. No login is required. Leave the remote access
variables unset for this mode.

## Standalone CLI remote browser (private deployment)

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

Remote Endpoint v1's primary mode is a zero-install **Remote Control** portable
worker with temporary in-memory credentials, foreground Disconnect/Exit and
explicit remembered mode. Its endpoint workspace contains Device Chat, Desktop,
Files, Processes, Browser and Connection. Device Chat uses the same canonical
ChatRuntime with persisted server-owned endpoint binding, separate history/mutation
mode and no Project/attachments. Cross-device endpoint calls are rejected.
Portable platform artifacts carry version/source SHA/checksums; source builds
without compatible release metadata show unavailable. Confirmed End & forget
removes endpoint-owned metadata/history under existing active-request safeguards.
See the endpoint operations/architecture reference for platform prerequisites,
cleanup/expiry, download integrity and native artifact smoke coverage.

## Windows Desktop Host Mode (opt-in)

Host Mode uses the desktop app's existing backend and managed data directory.
From the local Windows app, go to **Settings > Kết nối server > Tài khoản & Bảo mật**.
Set an Owner password of at least 12 characters, scan the Authenticator QR and
confirm the six-digit TOTP. Keep the single-use recovery codes somewhere private.
Initial configuration and credential changes require the authenticated Windows
Desktop channel. Previous native sessions are invalidated when setup completes.

If the first setup expires or the code is rejected, cancel the setup and create
a new QR. Scan the new QR and use the code from that entry. Desktop writes the
Owner record only after a correct confirmation. If the app exits mid-setup,
start again after reopening it.

If you lose the authenticator, use your current password and one unused recovery
code in **Thay đổi 2FA** on the Windows app. Confirm the new QR with the replacement
authenticator and save the new recovery codes. Password changes, replacing 2FA,
and **Đăng xuất tất cả thiết bị** invalidate remote browser and native sessions
and pending enrollment codes. Chat data and model configuration stay in the
managed data directory.

After Owner setup, select **Bật truy cập từ xa** in **Kết nối server**. Orion
detects the HTTPS URL from the signed-in Tailscale node, saves Host Mode, and
restarts if the managed backend needs a different listener. If Tailscale denies
permission, Windows may show a UAC prompt for the specific Serve operation.
Orion starts under the current account at Windows sign-in. Background Serve
persists across a Windows restart.

Settings shows the private URL, loopback upstream, and live HTTPS status. A
protected API answering 401 or 403 confirms HTTPS is responding. When the panel
confirms the Owner login path, use **Tạo QR kết nối** to enroll Android.
**Tắt truy cập từ xa** returns Orion to local mode and removes an Orion-created
mapping only if it still matches the original route. Matching mappings created
outside Orion are left in place. Private Serve requires both devices to be on
the tailnet. Funnel remains off.
See [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).

Open the HTTPS origin in a browser and enter the Owner password and an unused
Authenticator or recovery code. A TOTP accepted by Orion cannot be reused in
its 30-second window. For Android, use **Tạo QR kết nối** on Desktop and
**Quét QR** on Android. Verify the HTTPS address shown on the phone against
Desktop, then enter the Owner password and a fresh authentication code.
Enrollment codes expire after five minutes and can be exchanged once. Android
stores the issued session in its Keystore-backed vault. Revoke a device from
Desktop or sign out on the device.

For a controlled Desktop deployment without Saved Settings, set
`ORION_DESKTOP_HOST_MODE=1`, `ORION_REMOTE_ACCESS=1`, and `ORION_PUBLIC_ORIGIN`
to the exact HTTPS origin. Set `ORION_ENDPOINTS=1` if paired endpoints are
needed. Leave `ORION_BIND_HOST` unset or use `127.0.0.1`. Configure the private
HTTPS proxy to target the loopback upstream shown by Orion. Owner credentials
come from the local Desktop setup.

Closing the Desktop window keeps Host Mode running. Reopen Orion and select
**Dừng server và đóng Orion** to stop it. Use **Tắt truy cập từ xa** to disable
Host Mode on later launches.
