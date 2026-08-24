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

## Model never calls the calculator

Check that the configured model supports OpenAI-compatible tool calls and continuation
after tool-result messages. The model receives the calculator schema on every call.
Do not add keyword routing as a workaround.

## Inspecting a request

Read `GET /api/requests/{request_id}/events` to reconstruct model and tool activity,
or `GET /api/sessions/{session_id}/timeline` for the persisted public conversation.
