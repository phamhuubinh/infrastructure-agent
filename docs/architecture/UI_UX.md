# UI and UX

## Navigation

The product navigation is **Chat | Projects | Remote Control | Commands | Settings**.
Settings configures model profiles/providers; it is not another runtime or a
per-chat tool selector. The target is shared conversation behavior with clearly
separated data and device selection.

## Shared conversation behavior

Chat, Project and Device Chat use the same composer, streaming, tool activity,
source rendering, cancellation and exact-call confirmation behavior. Only the
accepted terminal answer is presented as the answer to a user request; intermediate
tool-turn text stays activity/context. Provisional deltas are cleared when the
runtime resumes or repairs a turn.

Each conversation shows `read_only`, `confirm` or `auto` near the model control.
The mode persists independently for that conversation. Server and local worker
policy may still deny an action. Cancellation or disconnection after dispatch
must never be presented as proof that a change did not occur.

No tool checkboxes, RAG/OS-specific tool modes or per-message tool picker are required.
Tool activity and results provide transparency without asking the user to
orchestrate the runtime.

## Projects and documents

A Project workspace contains metadata/instructions, its conversations and
documents with ingestion status and source navigation. The document list and
composer use one shared state so ready/deleted files update without a chat request
or reload. Ready is a data state, not an artificial animation duration.

Project knowledge is not a separate assistant. Do not show a project agent,
model team or separate routing configuration.

## Remote Control landing page

Show compatible Windows/Linux portable worker downloads, version and checksum
metadata, pairing-code creation/expiry and the known device list. Development or
unmatched builds show artifact unavailable instead of a fabricated download.

Device rows show safe name, platform/OS, online/offline, temporary/remembered mode,
capabilities and last seen. A friendly name is a label; server-owned identity binds
the selected target.

## Device workspace

```text
KH-A-PC01 · Windows · Online
Chat | Commands | Connection
```

| View | Behavior |
| --- | --- |
| Chat | Endpoint-owned conversation/history and independent mutation mode |
| Commands (target) | Exact target/shell/command, running state, bounded stdout/stderr, exit/timeout and Stop |
| Desktop | Capability-aware view session; explicit manual control toggle and Stop |
| Files | Scoped browsing/transfer; explicit overwrite and cancellation state |
| Processes | Bounded process data and permitted operations |
| Browser | Worker-owned isolated browser operations and availability |
| Connection | Pair/session state, safe metadata, disconnect/revoke and End & forget |

Chat/Commands/Connection are the primary target workflow. Existing Desktop/Files/
Processes/Browser views are secondary, not command-execution prerequisites.
The shared Commands page observes session-owned command metadata, bounded output
cursors and canonical cancellation; creation remains the authorized Chat/Device
Chat tool path. It does not directly execute scripts or replay a command on
disconnect. See [the contract](SYSTEM_COMMANDS.md).

## Shared client implementation

The web client is a static React/Vite SPA served from `dist/client/_shell.html`;
there is no TanStack Start/Nitro server runtime. The router owns one QueryClient.
Mobile bottom navigation provides the same five destinations as the sidebar.
Native host bridges and secure vaults are separate platform implementation gates.

Runtime server profiles store only public id/name/origin metadata. Browser server
selection navigates to that origin and keeps cookie/Origin authentication intact.
Native clients inject their HTTP and secure-token-store adapters. Switching
server or authentication context aborts old response bodies and observations,
clears cached scope state and prevents stale cleanup from contacting the new
context. Provider secrets are referenced by server-owned credentials.

Chat admits an immutable content/session/UUID intent once and reconnects by GET
with durable event cursors. Stop uses the same nonce, including when admission
acknowledgment was lost, and waits for canonical terminal status. If completion
wins the race, the UI preserves completion. A lost observation never resubmits
the model/tool loop. Settings exposes vendor profiles, doctor, scoped skills/jobs,
MCP lifecycle and native session administration through the shared SDK.

See [R13 evidence](../refactor/evidence/R13_SESSION_2026-11-01.md) for exact web
fixture coverage and the remaining native/mobile/live acceptance limits.

Switching devices opens the other workspace. An active Device Chat never silently
changes endpoint. Device conversations do not appear in ordinary Chat/Projects and
inherit none of their documents/attachments. Offline history remains accessible;
calls display normal offline failures without corrupting conversation state.

Manual desktop control is a direct user action. A model confirmation grants only
that model call, not a manual control session. On reconnect, stale input is not
replayed and control must be reopened.

End & forget names the device and explains deletion of endpoint-owned history.
It confirms explicitly and respects active-request/run safeguards.

## Worker-facing experience

The portable worker shows connected/disconnected status and explicit Disconnect/
Exit. Temporary pairing is the default. Local capabilities are configured on the
machine and cannot be widened by changing an Orion conversation mode. Explain
platform/browser prerequisites when a capability is unavailable.

Portable means no installation/persistence setup, not removal of OS/security
telemetry. Separately provisioned browser caches are distinguished from worker
session temporary files.
