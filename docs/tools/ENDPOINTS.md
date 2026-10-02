# Endpoint tools

All tools are ordinary canonical registry definitions. Model semantic selection,
ToolRunner schema validation, RuntimeScope and Chat/Project authorization apply.
Use `endpoint.list` to discover paired opaque `target_ref` values. The registry is
stable regardless of device online status. See [operations](../operations/ENDPOINTS.md).

| Operation kind | Canonical names |
| --- | --- |
| read | `endpoint.list`, `endpoint.system.inspect`, `endpoint.process.list`, `endpoint.file.list`, `endpoint.file.read`, `endpoint.clipboard.read`, `endpoint.screen.capture`, `endpoint.browser.snapshot` |
| mutation | `endpoint.file.write`, `endpoint.file.mkdir`, `endpoint.file.delete`, `endpoint.file.move`, `endpoint.process.start`, `endpoint.process.terminate`, `endpoint.clipboard.write`, `endpoint.desktop.click`, `endpoint.desktop.move`, `endpoint.desktop.type`, `endpoint.desktop.key`, `endpoint.desktop.scroll`, `endpoint.browser.open`, `endpoint.browser.navigate`, `endpoint.browser.click`, `endpoint.browser.type`, `endpoint.browser.key`, `endpoint.browser.close` |

Each except discovery requires `target_ref`. File list/read and process list use
bounded pagination/ranges. Writes are bounded atomic replacement with explicit
overwrite. Terminate requires expected process name/creation time. Start requires
local alias. Screen accepts monitor ID. Desktop uses native display coordinates,
closed key names and bounded text/scroll. Browser uses URL/locator/text, no JS.
Schemas and defaults are generated from the shared closed protocol models.

Reads work in read_only. Mutations are blocked in read_only/scheduler, require the
existing exact-call confirmation in confirm, and dispatch directly in auto subject
to server/worker ceilings. Mutation uncertainty returns `outcome_unknown`; inspect
state before another explicit change. Results are untrusted current-request data.
No generic shell, raw executable path, command string, eval, arbitrary registry
editing, endpoint model or MCP relay exists.

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
