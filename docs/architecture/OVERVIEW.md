# Architecture overview

## Design statement

Orion is a **model-native capability harness for infrastructure operations**.

The model interacts with ordinary tools and tool results. The harness owns tool exposure, authority, policy, execution, evidence, limits, and terminal acceptance.

## Planes

```text
User / UI / API
      |
      v
+------------------+
| Session Runtime  |
+------------------+
      |
      v
+------------------+        dynamic tools
| Model Adapter    | <-----------------------+
+------------------+                         |
      | tool call                            |
      v                                      |
+------------------+                         |
| Tool Exposure    | -- search/load ---------+
+------------------+
      |
      v
+------------------+
| Authority Engine |
+------------------+
      |
      v
+------------------+
| Permission /     |
| Approval / Budget|
+------------------+
      |
      v
+------------------+
| Execution Boundary|
+------------------+
      |
      v
+------------------+
| Executor Registry|
+------------------+
      |
      v
+------------------+
| Evidence Store   |
+------------------+
      |
      +---- ToolResult ----> Model
```

## Ownership

### Model owns

- natural-language interpretation;
- reasoning;
- deciding whether more evidence is needed;
- proposing a tool call from currently exposed tools;
- composing the user-facing answer;
- referencing evidence IDs when making objective claims.

### Harness owns

- which tools are visible/callable now;
- parsing and validating model output;
- exact capability, target and source identity;
- argument schema validation;
- permission, approval and budget;
- idempotency and duplicate suppression;
- execution isolation;
- evidence creation and storage;
- runtime limits and no-progress detection;
- final evidence-reference validation.

## Hard invariants

1. A tool call is a proposal, not authority.
2. Registered is not the same as exposed.
3. Exposed is not the same as authorized.
4. Authorized is not the same as executed.
5. Executed is not the same as successful.
6. Successful is not the same as evidenced unless an evidence record exists.
7. User-facing prose is not an authority channel.
8. Provider-native structured output is not the final validation boundary.
9. No implicit target/source/default-localhost behavior.
10. No parallel legacy runtime after cutover.

## Why this design

Coding agents such as Codex and Claude Code are reliable partly because models interact with actual tools rather than narrating an internal workflow protocol. Orion adopts that model-native loop but narrows the action surface to reviewed infrastructure capabilities and adds stronger logical authority before execution.
