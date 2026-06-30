# Message Types
ACTION
The reasoning model requests the Agent to execute one action.
OBSERVATION
The Agent returns raw execution results exactly as produced by the execution environment.
FINAL
The reasoning model finishes the interaction and produces the final response.
User Request
↓
Model
↓
ACTION
↓
Agent
↓
Observation
↓
Model
↓
ACTION
↓
...
↓
FINAL
↓
User
