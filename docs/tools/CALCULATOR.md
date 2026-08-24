# Calculator

## Purpose

Provide deterministic computation when the model wants exact arithmetic or other supported numeric operations.

## Behavior

The calculator is automatically available like every other registered tool.

The model decides when to use it. Orion should not regex-route arithmetic prompts before the model.

## Result

Return structured values, not prose-only output.

Example conceptual result:

```json
{
  "operation": "multiply",
  "value": "120253"
}
```

The model may then use the result in its final answer or another calculation.

## Testing

Calculator tests should verify:

- correct deterministic values;
- invalid input errors;
- structured result shape;
- clean tool-call → ToolResult → model continuation.
