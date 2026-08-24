# Orion documentation

This documentation is the target specification for Orion.

## What Orion is

Orion is a local-first AI technical workbench centered on conversation:

```text
Chat
  → general conversation
  → session attachments
  → all registered tools used automatically by the model

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

- `architecture/OVERVIEW.md`
- `architecture/CHAT_RUNTIME.md`
- `architecture/PROJECT_RUNTIME.md`
- `architecture/MODEL_TOOL_LOOP.md`
- `architecture/TOOL_SYSTEM.md`
- `architecture/RAG_AND_PROJECT_KNOWLEDGE.md`
- `architecture/CONTEXT_AND_MEMORY.md`
- `architecture/MODEL_BACKENDS.md`
- `architecture/DATA_AND_PERSISTENCE.md`
- `architecture/BACKEND_API.md`
- `architecture/UI_UX.md`
- `architecture/OBSERVABILITY.md`
- `architecture/FAILURE_RECOVERY.md`
- `architecture/SECURITY_LOCAL_FIRST.md`

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

The docs describe the desired system. The repository may temporarily contain older routing, agent protocol, capability, or evidence code while implementation catches up.

Do not preserve an obsolete implementation merely because it exists. Conversely, do not delete or rewrite code merely because you read this document: repository modifications require an explicit current task.
