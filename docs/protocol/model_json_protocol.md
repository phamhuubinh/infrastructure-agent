# Model JSON Protocol
---
# Purpose
The Model JSON Protocol defines the data exchange format between the reasoning model and the Agent.
The Agent communicates with the reasoning model exclusively through JSON messages.
---
# General Rules
The reasoning model shall return exactly one valid JSON object.
The reasoning model shall never return markdown.
The reasoning model shall never return explanations outside the JSON object.
---
# Response Types
The reasoning model may produce one of the following response types.
* action
* final
---
# Action JSON Schema
```json
{
    "type": "action",
    "tool": "<tool-name>",
    "arguments": {}
}
```
Required fields:
* type
* tool
* arguments
The "type" field shall be "action".
The "tool" field shall identify exactly one supported Agent tool.
The "arguments" field shall contain all tool arguments.
---
# Final JSON Schema
```json
{
    "type": "final",
    "content": "<message>"
}
```
Required fields:
* type
* content
The "type" field shall be "final".
The "content" field shall contain the final response for the user.
---
# Validation Rules
The reasoning model shall return exactly one JSON object.
Unknown response types shall be rejected.
Unknown tools shall be rejected.
Missing required fields shall be rejected.
Additional fields may be ignored by the Agent.
The Agent shall never infer missing information.
