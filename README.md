# Orion

Orion is a local, single-operator AI agent for project knowledge and infrastructure work.

> **Implementation baseline:** `259f85b` (`refactor(agent): remove legacy deterministic stack`).
> The configured Chat path uses the canonical model-driven agent runtime. The accepted target
> architecture is documented under `docs/`; where current implementation still differs from the
> target, the difference must be stated explicitly rather than hidden behind compatibility behavior.

## Architecture

Two rules define Orion's architecture:

> **The model owns language understanding, reasoning, and next-action proposals.**

> **The harness owns authority, validation, execution, evidence, limits, and completion.**

For normal configured Chat requests there is no language-specific semantic pre-router in front of
the model. The model produces one of the canonical decisions (`FINAL`, `ACTION`, `DISCOVER`,
`CLARIFY`, or `REFUSE`). An `ACTION` is only a proposal. The harness must validate the exact
capability, target/source references, arguments, permissions, budgets, and safety policy before any
tool can run.

```text
User request + bounded session context
    ↓
Canonical agent model
    ↓
FINAL / ACTION / DISCOVER / CLARIFY / REFUSE
    ↓
Capability discovery + exact authority validation
    ↓
Validated action only
    ↓
Executor → reviewed tool/capability runtime
    ↓
Normalized observation/evidence
    ↓
Agent model
    ↓
repeat while useful, within harness limits
    ↓
Final delivery + safe execution trace
```

Natural-language text is never execution authority. Unknown capabilities, targets, or sources fail
closed; Orion must not fuzzy-map them or silently fall back to localhost or another source.

### Current Chat and Project/RAG implementation

The canonical Chat runtime is the configured path used by Web/CLI construction. Session
attachments can be supplied to Chat as bounded, untrusted model context.

The current Project RAG service under `src/tool/RAGTool/` is still a standalone Web document
workspace and is **not currently registered as a Chat agent capability**. This is a current
implementation boundary, not the accepted long-term architecture. ADR-0003 requires Project
knowledge to become a normal READ capability inside the same agent loop.

## Permission model

Executable capabilities have an effect class:

- **READ** — observes or retrieves data without changing external state.
- **WRITE** — creates, changes, deletes, restarts, deploys, installs, or otherwise mutates state.

User modes are `READ`, `RW + ASK`, and `RW + FULL`. Permission is determined by the declared,
reviewed capability effect and structured authority state, not by matching English/Vietnamese
mutation keywords.

## Configuration

### Infrastructure tools

Infrastructure tool configuration is split by sensitivity:

- `tools.json` — tracked, non-secret tool registry. Do not put credentials in it.
- `/etc/orion/tool-credentials.json` — deployment endpoints and credentials outside the source
  checkout, mounted read-only into the API container.

Example:

```json
{
  "grafana": {
    "url": "http://your-grafana:3000",
    "token": "your-grafana-token"
  },
  "zabbix": {
    "url": "http://your-zabbix/zabbix",
    "token": "your-zabbix-token"
  }
}
```

A template is available at `config/tool-credentials.example.json`.

If `/etc/orion/tool-credentials.json` is absent, `./install.sh` creates a private empty `{}` file,
skips unavailable Grafana/Zabbix setup, and reports missing fields. After adding credentials, run:

```bash
docker compose up -d --force-recreate api
```

### Internet access

Internet capabilities use reviewed bounded search/fetch implementations. The model may decide that
current public information is useful, but deterministic runtime controls still own SSRF protection,
DNS/redirect validation, timeouts, response-size limits, and execution authority.

### Models

Orion does not install or manage model runtimes or model weights. The configured agent core is
provider-neutral. Supported connections include OpenAI-compatible endpoints and provider adapters
implemented by the repository.

If no model is configured, Orion can still start and expose configuration/diagnostics. A request
that requires model reasoning returns a clear setup error rather than being semantically routed by
legacy deterministic keyword logic.

## Quick start

Docker Engine with Docker Compose is the main platform prerequisite.

```bash
./install.sh
# → http://localhost
# → `orion help` is available from the host shell
```

Configure or inspect a model connection from the containerized CLI:

```bash
docker compose exec api orion model list
docker compose exec api orion model add primary \
  --base-url https://api.openai.com/v1 \
  --model gpt-4.1 --api-key-stdin
docker compose exec api orion model test primary
```

The Web settings can also manage model connections. Loopback model endpoints such as
`http://localhost:11434` are mapped to the host in the Docker installation.

## Uninstall

```bash
./uninstall.sh
./uninstall.sh --yes
./uninstall.sh --dry-run
```

Uninstall removes Orion containers, project-built images, Docker volumes, model connections,
sessions, RAG projects/documents, logs, `.env`, and the host launcher. Interactive uninstall asks
separately whether `/etc/orion/tool-credentials.json` should be removed; `--yes` preserves that
shared credential file automatically. The source checkout and independently managed model runtimes
are preserved.

## CLI

```bash
orion help
orion run
orion web
orion log
orion model list
```

The host command is a lightweight Docker launcher. `orion web` starts the Web services when needed
and follows logs for that invocation; `Ctrl+C` stops those Web services. `orion log` follows the
Compose service logs and exits without stopping the stack.

## Development Web UI

For source-development mode:

```bash
# Terminal 1: Project RAG service
cd src/tool/RAGTool
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080

# Terminal 2: backend + Vite frontend
cd ../../..
python3 -m src.cli web
# → backend: http://localhost:61888
# → frontend: http://localhost:5173
```

The Project/document-analysis UI uses the standalone RAG service described above. Analysis requires
an active model; project/document lifecycle operations can remain available without one.

## Docker Compose

Use `./install.sh` for a complete first installation. Direct `docker compose up -d --build` is for
operators who already have `.env` and `/etc/orion/tool-credentials.json` prepared. An empty `{}` is
valid for the credentials file.

The RAG service is internal-only in the root Compose stack; browser requests pass through the API.

## QA

Unit/static validation and live runtime QA are separate classes of testing. The manual GA2 runners
can start Docker and make real model/tool requests, so run them only when that validation is
intended.

```bash
make test
make lint

# live runtime QA
make qa-smoke
make qa-full
```

Generated QA output is written under ignored `artifacts/qa/`.

## Documentation

`docs/` contains the accepted target architecture.

Start with `docs/README.md`. Its source-of-truth order is:

1. accepted ADRs in `docs/decisions/`;
2. architecture documents in `docs/architecture/`;
3. engineering/development documents in `docs/development/`;
4. product documents.

Current implementation facts are established by source code, tests, generated API schema, and
runtime evidence. They may reveal an implementation gap, but they do not silently override an
accepted ADR.

Additional references:

- `docs/api/` — generated API schema and generation rules;
- `scripts/qa/` — manual end-to-end/runtime QA;
- `src/tool/RAGTool/README.md` — current standalone Project RAG service implementation.
