# Agent Runtime

## Decision types

Exactly one of:

- **FINAL** — answer candidate;
- **DISCOVER** — request bounded capability metadata;
- **ACTION** — propose one registered/disclosed capability call;
- **CLARIFY** — ask for missing information/help;
- **REFUSE** — decline the request.

## Stage legality and progressive disclosure

Decision legality is stage-specific and is enforced by the harness after generation. Provider-native structured output/guided decoding is not the final correctness boundary.

### FIRST

The model sees the request and bounded capability **group names**, not arbitrary capability IDs.

Legal:

```text
FINAL | DISCOVER | CLARIFY | REFUSE
```

`ACTION` is illegal because no capability ID has been disclosed. `DISCOVER.category` must exactly match a currently disclosed group.

### DISCOVERY

Successful discovery exposes exact capability summaries from one group. The harness records what was actually disclosed.

The next decision receives those summaries and may select only their exact
capability IDs. DISCOVER is constrained to still-undisclosed groups; a
provider-ignored repeat of an already disclosed group creates no new state and
stops through the no-progress guard without consuming another discovery call.

A known registry capability is not equivalent to a disclosed capability.

### ACTION_DETAIL

When one capability's detail/schema is disclosed, `ACTION` must use that exact capability ID and satisfy the exact closed argument/target/source schema. The provider action schema is generated from that same disclosure: non-applicable refs are omitted, and applicable refs are exact disclosed enums. Runtime reference validation remains authoritative.

### OBSERVATION / FEEDBACK

The model receives bounded structured feedback/observations and can choose the next legal decision. New actions remain subject to disclosure and authority validation.

A future protocol may expose capabilities earlier, but legal IDs must always be explicit harness state.

## Branch field exclusivity

- FINAL → `answer`, with `claims` only when evidence is asserted
- DISCOVER → `category`
- ACTION → `action`
- CLARIFY → `question`
- REFUSE → `reason`

The v3 wire contract contains `version`, `kind`, and only the selected branch
field. It does not accept unrelated nullable fields or a model-generated
`goal`; authority remains harness-owned structured state.

## Protected internal information

Requests whose goal is to reveal/reproduce system/developer prompts, hidden policies/internal instructions, credentials/secrets, or private hidden reasoning terminate as `REFUSE`. The agent must not use discovery/actions to obtain protected internal information.

This policy is model-semantic plus deterministic output/security enforcement; it is not a language-specific keyword router.

## Loop/no progress

The harness never invents a semantic alternative after rejection.

No-progress includes repeated identical action/result, repeated forbidden-stage decision, repeated undisclosed capability proposal, repeated invalid discovery, or feedback cycles that add no evidence/disclosure/authority state.

Do not raise model-call limits to hide a deterministic feedback loop.

## Direct answers/model identity

Direct FINAL is valid when no capability is needed. Objective runtime facts such as configured model/provider identity must be grounded in safe machine-readable configuration; model self-description is not evidence.
