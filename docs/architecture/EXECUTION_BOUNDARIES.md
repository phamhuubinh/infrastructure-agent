# Execution boundaries and sandboxing

## Purpose

Authority defines what an action is allowed to mean. Execution boundaries limit what the implementation can physically reach if it is buggy, compromised, or manipulated by untrusted data.

## Layers

```text
ToolCall proposal
  -> authority
  -> permission / approval / budget
  -> execution boundary
  -> executor
  -> external system
```

## Boundary mechanisms

Use the strongest practical combination per executor:

- OS sandbox or container isolation;
- filesystem read/write boundaries;
- outbound network allowlists;
- per-integration service accounts;
- restricted SSH accounts/keys;
- command allowlists or fixed command construction inside reviewed tools;
- seccomp/AppArmor/Landlock/bubblewrap where suitable;
- resource/time/output limits;
- separate processes for risky integrations.

## Credentials

Credentials are executor configuration, not model arguments. They are resolved after authorization using exact target/source configuration. Never put secrets into tool schemas, model prompts, evidence facts, or ordinary events.

## Network

Default deny is preferred for generic execution environments. Network-capable executors should have destination policy derived from exact configured integration/target identities. Redirects and DNS resolution must not silently escape the allowed destination set.

## Shell

Orion should not expose generic root shell as its normal model capability. Reviewed host capabilities may internally execute fixed/parameterized commands, but command construction belongs to the tool implementation and must be validated independently of model prose.

## Sandbox vs permission

Following the useful separation seen in modern coding agents:

- permission controls whether a tool is allowed to run;
- sandbox/isolation controls what the resulting process can access.

For Orion, logical capability authority is an additional layer before both.

## Failure behavior

If the configured boundary cannot be established for a capability that requires it, fail closed. Do not silently fall back to unrestricted execution.
