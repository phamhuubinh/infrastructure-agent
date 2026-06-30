# Model Response
---
# Purpose
Model Response represents exactly one reasoning decision produced by the reasoning model.
A Model Response may request another action or terminate the reasoning session.
---
# Response Types
The reasoning model may produce one of the following responses:
* Action
* Final
---
# Action
An Action requests the Agent to perform exactly one operation.
Examples:
* execute a shell command;
* read a file;
* connect through SSH;
* retrieve session context.
The Agent executes the Action and returns an Observation.
---
# Final
A Final response terminates the reasoning session.
The Final response contains the reasoning model's answer for the user.
No further Actions shall be executed after a Final response.
---
# Architectural Constraints
A Model Response shall represent exactly one decision.
The reasoning model shall never produce both an Action and a Final response simultaneously.
