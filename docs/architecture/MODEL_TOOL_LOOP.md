# Model-tool loop

## Core contract

The model is called with conversation context and the complete set of currently registered tool definitions.

The model may return:

- normal assistant content/final answer;
- one or more provider-supported tool calls.

Provider adapters normalize these into Orion's internal message/tool-call contracts.

## Canonical loop

```text
while model has not produced a final answer:
    model_output = model(context, registered_tools)

    if model_output contains tool call:
        validate tool name + input schema
        result = execute registered tool
        append tool call + ToolResult to conversation context
        continue

    return assistant answer
```

This is a model-native tool loop, not an Orion-visible workflow state machine.

## No old workflow protocol

Do not require the model to emit or memorize states such as:

- DISCOVER;
- SELECT;
- ACTION;
- ACTION_DETAIL;
- OBSERVATION;
- FEEDBACK;
- completion obligations.

A tool call is simply a tool call. A tool result is simply a tool result.

## Automatic tool use

"Automatic" means:

- user does not choose a tool;
- Orion does not choose the semantic tool before the model;
- the model chooses;
- Orion executes the chosen registered tool.

## Tool availability

For the current architecture:

```text
registered/configured tool
        =
available to the model
```

There is no `capability.search`, deferred tool exposure, namespace-loading protocol, or per-request tool allowlist in the target.

If the tool catalog becomes too large in the future, changing this requires a new explicit architecture decision rather than silently reintroducing dynamic exposure.

## Multiple calls

The runtime should support natural sequential use:

```text
model → project search
result → model
model → document read
result → model
model → calculator
result → model
model → final
```

Parallel provider tool calls may be supported where tool implementations and provider adapters support them safely; sequential correctness is the baseline.
