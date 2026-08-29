# Orion documentation

This documentation is the target specification for Orion, with operations pages explicitly marked where they describe current repository behavior.

## What Orion is

Orion is a local-first AI technical workbench centered on conversation:

```text
Chat
  → general conversation
  → session attachments
  → registry-derived tools catalog available automatically to the model

Project
  → same Chat runtime
  → same registered tools
  → persistent project metadata/documents
  → additional project-scoped RAG source
```

There is no tool picker in Chat or Project.

## Read in this order

### Product

- `PRODUCT.md`
- `QUICKSTART.md`

### Architecture

1. `architecture/OVERVIEW.md`
2. `architecture/CONTRACTS.md`
3. `architecture/CHAT_RUNTIME.md`
4. `architecture/PROJECT_RUNTIME.md`
5. `architecture/MODEL_TOOL_LOOP.md`
6. `architecture/TOOL_SYSTEM.md`
7. `architecture/RAG_AND_PROJECT_KNOWLEDGE.md`
8. `architecture/CONTEXT_AND_MEMORY.md`
9. `architecture/MODEL_BACKENDS.md`
10. `architecture/DATA_AND_PERSISTENCE.md`
11. `architecture/BACKEND_API.md`
12. `architecture/UI_UX.md`
13. `architecture/OBSERVABILITY.md`
14. `architecture/FAILURE_RECOVERY.md`
15. `architecture/SECURITY_LOCAL_FIRST.md`

`CONTRACTS.md` defines the canonical identities shared by the runtime. Other architecture documents should refer to these concepts rather than inventing competing representations.

### Tool families

- `tools/README.md`
- `tools/KNOWLEDGE_RAG.md`
- `tools/CALCULATOR.md`
- `tools/INTERNET.md`
- `tools/LINUX.md`
- `tools/GRAFANA.md`
- `tools/ZABBIX.md`
- `tools/ADDING_A_TOOL.md`

### Running Orion

- `operations/INSTALLATION.md`
- `operations/LOCAL_RUN.md`
- `operations/DOCKER.md`
- `operations/CONFIGURATION.md`
- `operations/MODELS.md`
- `operations/RAG_SERVICE.md`
- `operations/TROUBLESHOOTING.md`

Operations pages that say **current** must be verified against the actual scripts/Compose configuration when they are changed.

### Development

- `development/TARGET_CODE_LAYOUT.md`
- `development/ENGINEERING_RULES.md`
- `development/TESTING.md`
- `development/ACCEPTANCE_CRITERIA.md`
- `development/REBUILD_GUIDE.md`
- `development/CLEANUP.md`

### Decisions and reference

- `decisions/README.md`
- `reference/GLOSSARY.md`
- `reference/ARCHITECTURE_PRINCIPLES.md`

## Target docs vs current code

Architecture/product docs describe the desired system.

The repository may temporarily contain older routing, agent protocol, capability, or evidence code while implementation catches up.

Operations docs are different: when they describe current commands, service names, ports, installer flags, or configuration files, those facts must match the current repository.

Do not preserve an obsolete implementation merely because it exists. Conversely, do not delete or rewrite code merely because you read this document: repository modifications require an explicit current task.
