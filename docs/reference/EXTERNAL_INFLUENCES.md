# External architectural influences

Snapshot date: 2026-08-24.

This clean-sheet design borrows patterns, not source code or product-specific assumptions.

## OpenAI Codex / Agents

Useful patterns:

- model-native harness where models work with real tools;
- tool calls represented as lifecycle items;
- approvals can pause execution until allow/deny;
- sandbox and network policy constrain command execution;
- deferred/tool-search loading avoids sending a huge tool catalog up front;
- stable agent loop separates model inference from local/runtime execution.

References:

- https://openai.com/index/unlocking-the-codex-harness/
- https://openai.com/index/running-codex-safely/
- https://openai.com/index/building-codex-windows-sandbox/
- https://openai.com/index/the-next-evolution-of-the-agents-sdk/
- https://openai.github.io/openai-agents-python/tools/

## Claude Code

Useful patterns:

- tools have explicit names and permission requirements;
- allow / ask / deny permission policy;
- tool permissions and OS-level sandboxing are complementary layers;
- filesystem/network boundaries protect against tool/subprocess escape;
- MCP/custom tools extend the model surface without changing the core conversation model.

References:

- https://code.claude.com/docs/en/tools-reference
- https://code.claude.com/docs/en/permissions
- https://code.claude.com/docs/en/sandboxing
- https://code.claude.com/docs/en/security

## Orion-specific differences

Orion should be stricter than a coding agent for privileged infrastructure:

- do not normally expose generic shell as the model's infrastructure authority;
- expose reviewed semantic capabilities instead;
- validate exact infrastructure target/source relationships before execution;
- keep credentials behind executors;
- require structured evidence for objective operation claims;
- treat capability authority as a distinct layer before permission and sandboxing.

The resulting formula is:

> Codex-style model-native tool loop + Claude-style permission/isolation separation + Orion-specific capability authority and evidence.
