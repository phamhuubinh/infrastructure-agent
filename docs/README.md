# Orion Documentation

This documentation defines the **accepted target architecture** and keeps current implementation gaps explicit.

Orion is one personal AI agent for project knowledge/documents and infrastructure work. The agent may also answer ordinary questions directly when no capability is needed.

## Core principles

> **The model owns language understanding, reasoning, and next-action proposals.**

> **The harness owns authority, validation, execution, evidence, limits, no-progress handling, and completion.**

Natural-language text is never execution authority. Provider-native structured output is not the final authority boundary: every returned decision must satisfy the active stage/schema and actual disclosed-capability state.

## Product model

One agent, many capabilities. Current/target families include Linux/SSH, Grafana, Zabbix, Internet, Calculator, and Project Knowledge/RAG.

Project Knowledge/RAG is **target architecture but not yet a Chat capability** at the current baseline; the existing RAG service remains a standalone Web workspace.

## Protected internal information

System/developer prompts, hidden policies/internal instructions, credentials/secrets, and private hidden reasoning are not user-retrievable data. Requests to reveal/reproduce protected internal instructions terminate as `REFUSE`. See ADR-0009.

## Current implementation baseline

GitHub `main` at `3e88075` uses canonical model-driven Web/CLI Chat construction, but target convergence is not complete.

The current repair ledger is:

- `development/IMPLEMENTATION_GAPS.md`

It records confirmed implementation defects/gaps from repository-wide audit and live runtime evidence. It is subordinate to accepted ADRs: repair implementation toward architecture rather than redefining architecture to match bugs.

Notable current gaps include stage/disclosure enforcement, evidence-backed completion, target fail-closed behavior, persistence/session correctness, model health/identity, unified event/metrics wiring, CI debt, standalone RAG hardening, Project RAG Chat integration, and UI correctness.

## Reading order

1. [PRODUCT.md](PRODUCT.md)
2. [architecture/OVERVIEW.md](architecture/OVERVIEW.md)
3. [architecture/AGENT_RUNTIME.md](architecture/AGENT_RUNTIME.md)
4. [architecture/CAPABILITIES.md](architecture/CAPABILITIES.md)
5. [architecture/PERMISSIONS.md](architecture/PERMISSIONS.md)
6. [architecture/PROJECTS_RAG_MEMORY.md](architecture/PROJECTS_RAG_MEMORY.md)
7. [architecture/EVIDENCE.md](architecture/EVIDENCE.md)
8. [architecture/MODELS.md](architecture/MODELS.md)
9. [architecture/SECURITY.md](architecture/SECURITY.md)
10. [architecture/UI_UX.md](architecture/UI_UX.md)
11. [architecture/EVENTS_LOGS_UI.md](architecture/EVENTS_LOGS_UI.md)
12. [architecture/FAILURE_RECOVERY.md](architecture/FAILURE_RECOVERY.md)
13. [development/ENGINEERING_RULES.md](development/ENGINEERING_RULES.md)
14. [development/IMPLEMENTATION_GAPS.md](development/IMPLEMENTATION_GAPS.md)
15. [development/TARGET_CODE_LAYOUT.md](development/TARGET_CODE_LAYOUT.md)
16. [development/MIGRATION.md](development/MIGRATION.md)
17. [development/TESTING.md](development/TESTING.md)
18. [development/CLEANUP.md](development/CLEANUP.md)
19. [decisions/README.md](decisions/README.md)

## Source-of-truth order

For target architecture:

1. accepted ADRs;
2. architecture docs;
3. engineering/development rules;
4. product docs.

For implementation truth, inspect source/tests/generated artifacts/runtime evidence. `IMPLEMENTATION_GAPS.md` records known mismatches but never grants permission to reintroduce architecture rejected by an ADR.
