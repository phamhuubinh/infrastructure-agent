# Model backends

## Provider-neutral core

The Chat/Project runtime should depend on a small provider-neutral interface.

Conceptually:

```python
class ModelBackend:
    async def complete(self, messages, tools, settings): ...
    async def stream(self, messages, tools, settings): ...
```

Adapters translate provider-native messages/tool calls to and from Orion's internal contracts.

## Local-first model support

OpenAI-compatible local serving is a first-class target, including vLLM-compatible endpoints.

Remote providers may also be supported, but the core runtime must not depend on provider-specific response object types.

## Tool calling

Preferred order:

1. reliable native provider tool calling;
2. reliable structured tool-call format supported by an OpenAI-compatible endpoint;
3. a small strict JSON compatibility adapter only when native tool calls are unavailable.

Do not rebuild an Orion-specific multi-stage state protocol for weak providers.

## Model configuration

Model configuration should include only what is needed to connect/invoke:

- provider type;
- base URL;
- model ID;
- API key reference where required;
- context window or known model limits;
- temperature/reasoning settings where supported;
- timeout/retry transport settings.

Model identity comes from configuration, not from asking the model to identify itself.

### Request deadline settings

`ORION_MODEL_STREAM_TIMEOUT_SECONDS` remains an adapter-local provider transport
inactivity timeout. It is distinct from the monotonic request budget enforced by
`ChatRuntime`: `ORION_REQUEST_DEADLINE_SECONDS` defaults to 120 seconds (10–900),
and `ORION_REQUEST_FINALIZATION_RESERVE_SECONDS` defaults to 5 seconds (1–60 and
strictly less than the request deadline). The stream timeout defaults to 30 seconds
and must be in the inclusive 1–300 second range. Invalid values fail startup
validation; Orion does not clamp them.

The runtime derives a work deadline by subtracting the reserve. Conversation-state
preparation, ordinary model/tool work, and required verification must finish before
that boundary; the reserve is only for terminal persistence, terminal events, and a
future deterministic incomplete fallback. `ORION_QA_REQUEST_TIMEOUT_SECONDS` is a
