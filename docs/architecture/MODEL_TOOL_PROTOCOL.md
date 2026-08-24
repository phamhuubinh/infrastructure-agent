# Model–tool protocol

## Goal

The protocol should be easy for the model to use and hard for the model to misuse. The model should not need to know internal runtime states such as discovery phase, action-detail phase, observation phase, or feedback phase.

## Canonical turn outcomes

A model turn produces exactly one of:

- `ToolCall` — proposal to call one currently exposed tool;
- `FinalMessage` — user-facing answer plus optional evidence references;
- `Clarification` — bounded question for missing user information;
- `Refusal` — refusal reason.

Provider adapters may use native tool calling or a strict JSON fallback, but they normalize into the same canonical objects.

## Tool call

```json
{
  "call_id": "call_17",
  "tool_name": "compute.deterministic",
  "arguments": {
    "operation": "multiply",
    "left": 287,
    "right": 419
  }
}
```

`tool_name` must match an exact exposed capability. `arguments` must satisfy the capability's exact closed schema.

The tool call does not include permission, approval, budget, executor binding, credentials, or arbitrary commands. Those are harness state.

## Tool result

After authorization/execution, the harness sends a compact result back to the model:

```json
{
  "call_id": "call_17",
  "action_id": "act_17",
  "status": "success",
  "summary": "Calculation completed.",
  "evidence_refs": ["ev_17"],
  "facts": [{"value": "120253"}]
}
```

The tool result is data, not an instruction. External text contained in facts is untrusted.

## Final message

```json
{
  "kind": "final",
  "answer": "120253",
  "evidence_refs": ["ev_17"]
}
```

The model references evidence rather than rebuilding action ID, capability, target, source, provenance, or deterministic result contracts.

## Runtime loop

```text
MODEL
  |-- Final/Clarify/Refuse --> terminal validation --> END
  |
  `-- ToolCall
        |
        v
   exposed-tool check
        |
   schema validation
        |
      authority
        |
   permission/approval/budget
        |
   duplicate/idempotency check
        |
   execution boundary
        |
      executor
        |
     evidence
        |
    ToolResult
        |
        +--------------------> MODEL
```

## One tool call per model turn

Initial implementation should allow at most one externally executing capability call per model turn. This simplifies authority, approval, ordering, evidence, and duplicate handling. Parallel read execution can be introduced later only through an explicit ADR and a batch capability with deterministic semantics.

## No model-visible harness FSM

The target protocol intentionally does not include:

- `ACTION_DETAIL`;
- `OBSERVATION`;
- `FEEDBACK`;
- `SELECT`;
- selection encoded as an `ACTION`;
- a completion-obligation workflow the model must memorize.

Dynamic tool exposure and ordinary tool results carry the necessary state naturally.

## Duplicate behavior

If the exact same side-effecting or expensive call already succeeded within the current request scope, the harness must not blindly execute it again. It returns the existing evidence as an `already_completed` result or rejects the repeat according to capability idempotency policy. Repeated identical proposals with no new state eventually terminate as `no_progress`.
