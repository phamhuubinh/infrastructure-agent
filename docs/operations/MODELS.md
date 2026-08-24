# Model configuration

## Local model

Orion should treat OpenAI-compatible local endpoints as a first-class deployment.

Typical fields:

```text
provider = openai_compatible
base_url = http://<model-host>:<port>/v1
model = <served-model-id>
api_key = optional/local placeholder if server requires it
```

Exact configuration commands/UI fields are implementation-defined.

## Requirements for good Orion behavior

A model endpoint should reliably support:

- normal chat completion;
- sufficient context for conversation + tool schemas + results;
- tool calling or a reliable structured fallback;
- continuation after ToolResult messages.

## Remote models

Remote OpenAI/Anthropic-compatible providers may be adapters on the same `ModelBackend` interface.

Do not fork Chat/Project runtime behavior by provider.

## Diagnosis

If direct chat works but tools do not:

1. inspect provider tool-call compatibility;
2. inspect serialized model-facing tool schemas;
3. inspect raw provider response in redacted debug logs;
4. inspect adapter normalization;
5. do not add a semantic router as a workaround.
