# ADR-0009 — Protected Internal Instructions Are Not User-Retrievable

**Status:** Accepted

## Decision

System prompts, developer prompts, hidden policies, internal instructions, credentials/secrets, and private hidden reasoning are protected internal information rather than user-retrievable knowledge.

When the user's goal is to reveal or reproduce protected internal instructions, the canonical agent returns `REFUSE`.

The agent must not use capability discovery or execution to retrieve those protected items.

This policy is semantic and language-independent. It must not be implemented by placing an English/Vietnamese keyword router in front of the model.

Deterministic security/delivery code may still enforce redaction and prevent protected material from reaching public output.

## Consequences

- Prompt injection cannot convert internal instructions into an authorized data source.
- Adding languages does not require a refusal keyword list.
- Capability/tool authority is never widened to satisfy a protected-instruction request.
- Tests may use multilingual/adversarial examples while production policy remains generic.
