# Model JSON Protocol
## Purpose
Defines the communication protocol between the Reasoning Model and the Agent.
The protocol is independent of the underlying model implementation.
---
# Response Types
The Reasoning Model shall return exactly one JSON object.
Supported message types:
- action
- final
---
# Action
```json
{
    "type": "action",
    "tool": "<tool-name>",
    "arguments": {}
}
```
Required fields:
- type
- tool
- arguments
Rules:
- One Action per response.
- One Tool per Action.
- Arguments must be complete.
- Agent never infers missing arguments.
---
# Final
```json
{
    "type": "final",
    "content": "<message>"
}
```
Required fields:
- type
- content
Rules:
- Final terminates the reasoning session.
- Final never contains executable actions.
---
# Validation
The Agent shall reject:
- Invalid JSON.
- Unknown message types.
- Unknown tools.
- Missing required fields.
The Agent shall never modify Model output.
---
# Design Rules
- One response → One JSON object.
- One Action → One Tool.
- One Tool → One Observation.
- The protocol is stateless.
