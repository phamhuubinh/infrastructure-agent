# Orion documentation

> Current authority: [master request](../REFACTOR_REQUEST.md),
> [design](refactor/DESIGN.md), [providers](refactor/PROVIDERS.md),
> [work plan](refactor/WORK_PLAN.md), [acceptance](refactor/ACCEPTANCE.md)
> and [state](refactor/STATE.json). ADR 0018 supersedes conflicting older design.

This documentation separates current target design, inspected source and verified
operations. The product is **Chat | Projects | Remote Control**, using one main
model/runtime plus tools/skills and model-free remote workers.

## Read first

1. [ADR 0016 — runtime design](decisions/0016-single-runtime-redesign.md) and
   [ADR 0017 — command focus](decisions/0017-windows-linux-command-focus.md)
2. [Consolidated baseline — Vietnamese](architecture/BASELINE_2026-10-29.md)
3. [Product](PRODUCT.md)
4. [Architecture overview](architecture/OVERVIEW.md)
5. [Implementation inventory and verification limits](development/IMPLEMENTATION_STATUS.md)

Compatible earlier ADRs retain their detailed contracts. A closed issue is not
test evidence. Windows/Linux command execution is the primary OS target; dedicated monitoring
adapters are retired. Both command-runner and skill loading are design targets; existing MCP, scheduler and
endpoint source must not be described as missing.

## Runtime and context

- [Canonical contracts](architecture/CONTRACTS.md)
- [ChatRuntime](architecture/CHAT_RUNTIME.md)
- [Project scope](architecture/PROJECT_RUNTIME.md)
- [Model-tool loop](architecture/MODEL_TOOL_LOOP.md)
- [Tool system](architecture/TOOL_SYSTEM.md)
- [Windows/Linux commands](architecture/SYSTEM_COMMANDS.md)
- [Skill target contract](architecture/SKILLS.md)
- [Model backends](architecture/MODEL_BACKENDS.md)
- [Context and memory](architecture/CONTEXT_AND_MEMORY.md)
- [RAG and project knowledge](architecture/RAG_AND_PROJECT_KNOWLEDGE.md)

## Product boundaries and lifecycle

- [UI and UX](architecture/UI_UX.md)
- [Backend/API](architecture/BACKEND_API.md)
- [Data and persistence](architecture/DATA_AND_PERSISTENCE.md)
- [Endpoint runtime and threat model](architecture/ENDPOINTS.md)
- [Scheduler](architecture/SCHEDULER.md)
- [Security](architecture/SECURITY_LOCAL_FIRST.md)
- [Observability](architecture/OBSERVABILITY.md)
- [Failure recovery](architecture/FAILURE_RECOVERY.md)

## Tool families and operations

- [Tool reference](tools/README.md)
- [Knowledge/RAG](tools/KNOWLEDGE_RAG.md)
- [Calculator](tools/CALCULATOR.md)
- [Internet](tools/INTERNET.md)
- [Windows/Linux command contract](architecture/SYSTEM_COMMANDS.md)
- [Endpoints](tools/ENDPOINTS.md)
- [Adding a tool](tools/ADDING_A_TOOL.md)

## Running Orion

- [Quickstart](QUICKSTART.md)
- [Installation](operations/INSTALLATION.md)
- [Local run](operations/LOCAL_RUN.md)
- [Configuration](operations/CONFIGURATION.md)
- [Models](operations/MODELS.md)
- [RAG service](operations/RAG_SERVICE.md)
- [Remote browser access](operations/REMOTE_ACCESS.md)
- [Portable/remembered endpoints](operations/ENDPOINTS.md)
- [MCP](operations/MCP.md)
- [Linux headless](operations/HEADLESS.md)
- [Troubleshooting](operations/TROUBLESHOOTING.md)

Operations pages must match actual scripts/configuration. A target document cannot
establish that a command, installer or platform feature works.

## Development and records

- [Source responsibilities](development/TARGET_CODE_LAYOUT.md)
- [Reconciliation guide](development/REBUILD_GUIDE.md)
- [Acceptance criteria](development/ACCEPTANCE_CRITERIA.md)
- [Testing](development/TESTING.md)
- [Engineering rules](development/ENGINEERING_RULES.md)
- [Cleanup](development/CLEANUP.md)
- [GitHub reset record](development/GITHUB_RESET_2026-10-29.md)
- [Decision index](decisions/README.md)
- [Principles](reference/ARCHITECTURE_PRINCIPLES.md)
- [Glossary](reference/GLOSSARY.md)

Reading these documents does not authorize code deletion, migrations or Git
publication. Preserve existing source and reconcile it against the current target
when the user requests implementation work.
