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
after tool-result messages. Orion initially sends the registry-derived generic
`orion.tools.expand` control; the model requests exact registered tool names and then
receives those full schemas request-locally. The canonical registry remains the source
of validation and execution authority. Do not add keyword routing or a user tool picker
as a workaround.

## Inspecting a request

Read `GET /api/requests/{request_id}/events` to reconstruct model and tool activity,
or `GET /api/sessions/{session_id}/timeline` for the persisted public conversation.
