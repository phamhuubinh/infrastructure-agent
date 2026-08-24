# Orion

Orion is a local, single-operator AI agent for project knowledge and infrastructure work.

> **Implementation baseline:** GitHub `main` at `3e88075` (`qa: migrate GA2 to canonical runtime contract`), built on the canonical-agent refactor at `259f85b`.
>
> Accepted target architecture lives under `docs/decisions/` and `docs/architecture/`. Current implementation truth comes from source code, tests, generated API schema, and runtime evidence. Known mismatches are tracked explicitly in `docs/development/IMPLEMENTATION_GAPS.md`; fix them toward the accepted architecture rather than hiding them behind compatibility behavior.

## Architecture

Two rules define Orion:

> **The model owns language understanding, reasoning, and next-action proposals.**

> **The harness owns authority, validation, execution, evidence, limits, no-progress handling, and completion.**

Normal configured Chat requests go to the canonical model-driven agent without a language-specific semantic pre-router. The model returns one of `FINAL`, `DISCOVER`, `ACTION`, `CLARIFY`, or `REFUSE`.

An `ACTION` is only a proposal. Before execution the harness validates the active decision stage, actual capability-disclosure state, exact capability/target/source identities, typed arguments, permission/approval, budget, and safety policy.

Provider-native structured output is a generation aid, not execution authority. The parsed decision must still satisfy the active stage/schema.

```text
User request + bounded session/project context
    ↓
Canonical agent model
    ↓
FINAL / DISCOVER / ACTION / CLARIFY / REFUSE
    ↓
Stage validation + capability disclosure + exact authority validation
    ↓
Validated action only
    ↓
Executor → reviewed capability runtime
    ↓
Normalized observation/evidence
    ↓
Agent model
    ↓
repeat while useful, within resource/no-progress limits
    ↓
Evidence-aware final delivery + safe trace
```

Natural-language text is never execution authority. Unknown/malformed capabilities, targets, sources, backend types, configuration, or stage decisions fail closed. Orion must not fuzzy-map an unknown identity or silently substitute localhost/another source.

## Current Chat and Project/RAG implementation

Configured Web/CLI Chat construction uses the canonical runtime. Session attachments can be supplied as bounded, untrusted context.

`src/tool/RAGTool/` is still a standalone Web Project/document workspace and is **not yet registered as a Chat capability**. ADR-0003 remains the target: Project knowledge becomes a normal READ capability in the same agent loop.

The root Compose stack keeps RAG internal. The standalone RAG development Compose has a broader exposure and is not hardened for an untrusted network; see `docs/development/IMPLEMENTATION_GAPS.md`.

## Permission model

Capabilities declare one reviewed effect:

- **READ** — observes/retrieves data without changing external state.
- **WRITE** — creates, changes, deletes, restarts, deploys, installs, or otherwise mutates state.

Modes are `READ`, `RW + ASK`, and `RW + FULL`. Permission is based on structured capability effect/authority, not English/Vietnamese mutation keywords.

## Protected internal information

System prompts, developer prompts, hidden policies/internal instructions, credentials/secrets, and private hidden reasoning are not user-retrievable data. Requests whose goal is to reveal/reproduce protected internal instructions terminate as `REFUSE`; the agent must not use discovery/actions to retrieve them. See ADR-0009.

## Configuration

### Infrastructure tools

- `tools.json` — tracked non-secret tool registry.
- `/etc/orion/tool-credentials.json` — deployment endpoints/credentials outside the checkout, mounted read-only.

Malformed authority/configuration fails closed.

### Targets

An explicit valid `localhost` target means the Orion runtime environment (inside Docker, the API container), not the physical host.

Malformed target JSON, unknown backend types, or an invalid configured target file must **not** synthesize a local backend. The actual `ORION_TARGETS_FILE` selected by the deployment must be validated.

### Models

Orion is provider-neutral and does not manage model weights/runtimes.

Configured model identity is machine-readable runtime state. User-visible claims about which model/provider Orion is using must be grounded in that configuration, not in model self-identification.

Model configuration and model health are separate states. A saved connection is not automatically healthy.

If no model is configured, Orion exposes setup/diagnostics and returns a clear setup error for model-requiring requests rather than invoking legacy keyword routing.

## Quick start

```bash
./install.sh
# http://localhost
```

```bash
docker compose exec api orion model list
docker compose exec api orion model add primary \
  --base-url https://api.openai.com/v1 \
  --model gpt-4.1 --api-key-stdin
docker compose exec api orion model test primary
```

Loopback model endpoints can be mapped to the host in the packaged Docker installation.

## CLI and sessions

```bash
orion help
orion run
orion web
orion log
orion model list
```

Session list/delete/clean must operate on a consistent persistence view and confirm destructive operations **before** mutation. Current gaps are tracked in `docs/development/IMPLEMENTATION_GAPS.md`.

## QA

Local unit/static checks and live runtime QA are separate gates.

```bash
make test
make lint

# explicit live runtime QA
make qa-smoke
make qa-full
```

GA2 must distinguish proposed/attempted/dispatched actions from successful evidence. `budget.actions_used` is a budget/dispatch counter and is not proof of tool success.

## Documentation

Start with `docs/README.md`.

Target-design precedence:

1. accepted ADRs in `docs/decisions/`;
2. `docs/architecture/`;
3. `docs/development/` engineering/migration rules;
4. product docs.

Implementation truth comes from source/tests/generated artifacts/runtime evidence. Known current mismatches are recorded in `docs/development/IMPLEMENTATION_GAPS.md` and do not override accepted ADRs.
