# Model-tool loop

## Core contract

The model is called with conversation context and the complete set of currently registered tool definitions.

The model may return:

- normal assistant content/final answer;
- one or more provider-supported tool calls.

Provider adapters normalize provider-native output into Orion's canonical runtime contracts defined in `CONTRACTS.md`.

## Canonical loop

```text
while model has not produced a final answer:
    model_turn = model(context, registered_tools)

    if model_turn contains tool calls:
        normalize ModelToolCall
        validate tool name + input schema
        attach deterministic RuntimeScope
        ToolResult = execute registered tool
        append public tool call + ToolResult to context/timeline
        continue

    return assistant answer
```

This is a model-native tool loop, not a model-visible Orion workflow state machine.

## Responsibility split

```text
Model owns:
- whether a tool is useful;
- which registered tool to call;
- semantic arguments such as query, expression, host operation parameters;
- whether another call is useful after seeing ToolResult;
- when to answer.

Orion owns:
- registered tool definitions;
- provider normalization;
- schema validation;
- session/project RuntimeScope binding;
- dispatch;
- public timeline persistence;
- ToolResult normalization.
```

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

- the user does not choose a tool;
- Orion does not choose the semantic tool before the model;
- the model chooses from registered tools;
- Orion executes the chosen registered tool with deterministic runtime scope.

## Tool availability

For the current architecture:

```text
registered/configured tool
        =
available to the model
```

There is no `capability.search`, deferred tool exposure, namespace-loading protocol, or per-request tool picker in the target.

If the catalog becomes too large in the future, changing this is a new architecture decision rather than an implicit optimization.

## Sequential and multiple calls

The runtime must support natural sequential use:

```text
model → project knowledge search
result → model
model → exact document read
result → model
model → calculator
result → model
model → final
```

Parallel provider tool calls may be supported where adapters and tool implementations support them correctly. Sequential correctness is the baseline.

## Failures

A tool failure produces a canonical error `ToolResult` and returns to the model.

The model may use another source, correct arguments, explain the failure, or ask the user.

Do not invent successful data when a tool failed.
