# Paired Windows/Linux endpoints

Enable server support with `ORION_ENDPOINTS=1` and restart Orion. Existing local
loopback mode remains login-free. Remote deployment uses the HTTPS Remote Access
origin and owner login described in [REMOTE_ACCESS.md](REMOTE_ACCESS.md).

Open **Remote Control** and choose the Windows/Linux portable download for the
running server version. The UI shows expected SHA-256 from trusted release metadata
bound to the installed server's exact source SHA. Source/dev builds without an
installed release manifest show **Artifact unavailable for this build**.

```text
OrionRemote-<version>-windows-x64.zip  → OrionRemote.exe + _internal/
OrionRemote-<version>-linux-x86_64.tar.gz → orion-remote + _internal/
```

Extract and run the executable directly. It includes Python and executor libraries;
no Python/pip, Node/npm, Git, source checkout, installer or administrator rights are
required. Linux portable releases target x86_64 glibc 2.35+; desktop input/capture
also requires an available X11 session. OS libraries/display policies still apply.
The Playwright driver is bundled; managed Chromium provisioning remains explicit:
`OrionRemote.exe browser install` / `./orion-remote browser install`.
This explicit command retains the managed runtime under `~/.orion-worker/browsers`
(`PLAYWRIGHT_BROWSERS_PATH` can override it). That separately provisioned runtime
cache is not session-temporary data and is not erased on Exit.

Create a temporary pairing code (one-use, five-minute countdown). The foreground
console prompts for server URL, display name, pairing code and local permissions.
Default temporary mode retains the issued device credential only in process memory.
Enter **Disconnect** or **Exit**, or Ctrl+C. Clean exit closes the worker channel,
invalidates the temporary credential server-side and removes the worker-owned
session temporary directory (browser downloads/staging). If the server is unreachable,
the credential expires within two minutes of its last heartbeat; abrupt process
exit likewise expires. Server restart invalidates temporary identities. A new
process requires a fresh pairing code. No installer, PATH/registry/Start Menu
mutation, service, task, autostart or inbound firewall rule is added. Orion does
not erase downloads, OS/EDR/audit/prefetch history or other security telemetry.

`--remember` is explicit persistent mode in the same binary. It retains a protected
identity at `--data` / `~/.orion-worker`; Exit disconnects but does not revoke that
remembered device. `--policy` loads strict local JSON; without it the operator makes
conservative foreground permission choices. No server request widens these ceilings.

Each endpoint opens its own workspace: **Chat | Desktop | Files | Processes |
Browser | Connection**. Device Chat has persistent endpoint-owned history and its
own read_only/confirm/auto mode. It reuses the canonical ChatRuntime/ToolRunner;
server-owned endpoint binding rejects calls to another device, and there is no
Project/RAG/attachment scope or ordinary Chat history. History remains available
offline; tools return bounded offline errors. **End & forget** explicitly confirms
revocation/deletion of endpoint metadata/audit and Device Chat, using normal active
request deletion safeguards. Cancel/finish any active request first.

Secondary developer/owner installation mode remains available as separate lightweight
`orion-worker-<version>-windows-x64.zip` / `orion-worker-<version>-linux-x86_64.tar.gz`.
The following Python-based commands describe only this optional mode.

Verify SHA256SUMS and `worker-manifest.json` source commit/file hashes. Extract
outside Orion and run:

```text
python install.py --destination "<private install directory>"
<install directory>/venv/bin/orion-worker configure
<install directory>/venv/bin/orion-worker pair --server https://orion.example --name "Lab Linux"
<install directory>/venv/bin/orion-worker run
```

On Windows use `venv\Scripts\orion-worker.exe`. Python 3.12+ and package-index
access for executor dependencies are prerequisites; Node/npm, server dependencies,
embeddings and model runtimes are unnecessary. Pair prompts for the short-lived
token; avoid shell-history secrets. Tests may use `ORION_PAIRING_TOKEN`. Credentials
are never needed as CLI arguments. `--data "<private state directory>"` or
`ORION_WORKER_DATA` sets the state location (default `~/.orion-worker`). Unix state
is mode 0700/files 0600. Windows installs an explicit user DACL before secret writes.

`configure` creates a conservative `policy.json` and refuses replacement. Edit it
locally; unknown fields fail validation. `worker/policy.example.json` documents all
fields: separate absolute read/write roots (up to 16 each), configured application
aliases, terminate, clipboard read/write, browser/download directory, desktop capture/control,
maximum frame rate (1–5 FPS) and resolution (320–1920 px). Paths with spaces work.
Roots must exist; access outside them, traversal, escaping symlinks, Windows UNC,
device namespace and alternate data streams are denied. Root deletion is denied.
Aliases bind an executable and fixed argv. Dynamic argv needs `allow_args: true`;
shell/interpreter executables are denied. No environment or command-line metadata
is exposed in process reads. Termination binds PID, expected name and creation time.

To enable browser automation, set `browser: true`, then explicitly run
`orion-worker browser install`. This provisions managed Chromium. Installation
never downloads a browser implicitly. Each worker run uses one isolated ephemeral
context with bounded semantic accessibility snapshots; user cookies/passwords are
never imported. Downloads are disabled until `browser_download_directory` is
configured inside a writable root; then at most two per context are stored under
random names there, with a 32 MiB directory ceiling and 30-second deadline. Popups
close immediately. Portable temporary browser mode uses its own session directory. Automation
navigation, click, fill, key and close are mutations under normal Chat permissions.
Use a local HTML fixture for testing; no public site/model is required.

Desktop capture and control are separately enabled. Windows requires an interactive
normal desktop; locked/UAC/secure desktop may deny capture/control. Linux needs
X11 and DISPLAY. Wayland and headless sessions advertise unavailable. Remote Desktop
opens a 30-minute ephemeral view session and an optional explicit control toggle.
One controller per endpoint; bounded JPEG NDJSON stream; no stale input replay on
reconnect. Stop closes the session. File uploads/downloads are capped at 32 MiB and
relayed in 48 KiB chunks. Upload stages then atomically publishes; overwrite is an
explicit UI checkbox/header, and cancellation cleans staging. Files never auto-run.

Chat example: “List my endpoints, then inspect CPU and memory on Lab Linux.” For
changes select normal `confirm` or `auto` conversation mode; local worker ceilings
still apply. Project adds knowledge scope; it uses exactly the same endpoint tools.
SSH targets and MCP remain separate integrations.

`status` reports only paired identity. `revoke-local` removes local credentials;
revoke on Orion first to invalidate stolen copies. Rename/revoke use the owner UI.
Re-pairing is explicit: revoke, remove local identity, issue a new token, pair again.
Re-run `install.py` at the same destination to update the wheel/launcher. Uninstall
with `python install.py --destination "..." --uninstall`; protected user state is
preserved. Interactive workers stop on Ctrl+C; no service or self-update daemon.

Connection/operation logs contain safe names and correlation IDs only. No tokens,
credential, file/clipboard/form contents or input text are logged. SQLite persists
safe endpoint identity/capabilities/timestamps/revocation and up to 1000 lifecycle
audit events. Restart starts every device offline and fails interrupted operations;
it never replays mutations. Worker reconnect backs off 1/2/4/8/16/30 seconds.
Heartbeat is 15 seconds, bounded liveness timeout, 1.5 MB messages, four in-flight
operations and one mutation per device. Local request timeout is a transport bound,
not a product tool-call quota.

Troubleshooting: offline devices need an active worker, correct TLS URL and durable
identity. Rejected pairing requires a fresh token; ten failures/minute temporarily
block bootstrap. Unavailable capability requires local policy/platform/browser
provisioning. `policy_denied` means a local ceiling; changing conversation mode
cannot widen it. `outcome_unknown` means an unverified dispatched mutation; inspect
state before explicitly issuing another change. Windows firewall needs outbound
HTTPS only. Linux Wayland should use an X11 session, never privilege bypass.
