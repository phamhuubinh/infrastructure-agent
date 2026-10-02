# Troubleshooting

## Orion does not start

Confirm the package is installed and start the local API directly:

```bash
./install.sh
orion web
```

## Model unavailable

Check the active OpenAI-compatible model configuration's base URL, model ID,
authentication, and reachability from the local process. A model failure becomes an
explicit request failure.

## Model never calls a registered tool

Check that the configured model supports OpenAI-compatible tool calls and continuation
after tool-result messages. Orion sends all registered model-callable tool schemas on the first model turn. The canonical registry remains the source of validation and execution authority. Confirm the expected ordinary tool is registered and inspect its ToolResult errors. Do not add keyword routing or a user tool picker as a workaround.

## Inspecting a request

Read `GET /api/requests/{request_id}/events` to reconstruct model and tool activity,
or `GET /api/sessions/{session_id}/timeline` for the persisted public conversation.

## Endpoint unavailable or uncertain

Check worker online state, local policy, managed Chromium provisioning and an
interactive Windows/X11 desktop. Wayland fails closed. A revoked credential cannot
reconnect; explicitly re-pair. After `outcome_unknown`, inspect state before issuing
a new mutation. See [ENDPOINTS.md](ENDPOINTS.md).

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
