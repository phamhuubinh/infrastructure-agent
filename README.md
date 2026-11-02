# Orion

> Current full-refactor request: [REFACTOR_REQUEST.md](REFACTOR_REQUEST.md).
> Design/providers/tasks: [docs/refactor](docs/refactor/DESIGN.md).
> Required AI vendors are DeepSeek, Claude and OpenAI. Windows app, Linux CLI/service,
> Android/iOS clients, real skills and MCP are target deliverables, not implemented
> by the specification-writing phase. Older installation text describes existing source.

Orion is a local-first AI technical workbench accessed through a web interface.
One main model/runtime handles conversation and calls tools or skills as needed.
Projects hold context, documents and history. Remote machines run model-free
workers; they do not run separate AI agents.

## Product

| Surface | Purpose | Runtime and data |
| --- | --- | --- |
| Chat | General conversation, attachments and technical tasks | Canonical ChatRuntime; conversation-owned history |
| Projects | Work with project instructions and documents | Same runtime; project-scoped knowledge and conversations |
| Remote Control | Download/pair workers and operate connected devices | Same runtime; endpoint-owned Device Chat plus manual controls |

Each Remote Control device workspace contains **Chat, Desktop, Files, Processes,
Browser and Connection**. Device Chat has separate history and a server-owned
endpoint binding. It inherits no ordinary Chat attachments or Project knowledge.

The user states the task without a tool picker. Chat, Project and Device Chat
receive all registered model-callable tool schemas on the first model turn from
the canonical registry. The model decides whether and which tools to call;
schema visibility does not grant execution permission. There is no semantic
pre-router or separate Project/device agent.

```text
Web UI → authenticated API → ChatRuntime → configured ModelBackend
                                  │
                                  ├── scoped context and Knowledge/RAG
                                  └── ToolRegistry / ToolRunner
                                           ├── calculator / Internet
                                           ├── Windows/Linux commands (target)
                                           ├── MCP and scheduler tools
                                           └── endpoint gateway ← outbound WSS ← worker
```

## Design and implementation status

The [2026-10-29 baseline](docs/architecture/BASELINE_2026-10-29.md) consolidates the
redesign. [ADR 0016](docs/decisions/0016-single-runtime-redesign.md) defines its
relationship to earlier decisions; [ADR 0017](docs/decisions/0017-windows-linux-command-focus.md)
focuses OS work on Windows/Linux commands. Read [Product](docs/PRODUCT.md),
[Architecture](docs/architecture/OVERVIEW.md) and the
[implementation inventory](docs/development/IMPLEMENTATION_STATUS.md) next.

Runtime, Knowledge/RAG, MCP, scheduler, endpoint worker and endpoint UI code are
present in this repository. Source presence does not establish that a deployment,
release artifact or test suite is working. The documentation update does not
rewrite application code or certify issue completion.

The target OS interface is real PowerShell/cmd or sh/bash commands through workers
or configured SSH; see [the command contract](docs/architecture/SYSTEM_COMMANDS.md).
Dedicated Grafana/Zabbix adapters are outside the target product. Their legacy
code still exists; the generic command family is not yet implemented.

Skills are reusable task instructions over existing tools. The target skill
contract is documented in [Skills](docs/architecture/SKILLS.md); an executable
skill loader has not been established by this source inventory.

## Install a release

Download the matching platform archive from GitHub Releases. Full Orion server
installation requires Python 3.12+; Node.js, npm, Git and a source checkout are
not required for a server release installation.

Linux x86_64:

```bash
tar -xzf orion-<version>-linux-x86_64.tar.gz
cd orion-<version>-linux-x86_64
./install.sh
orion
```

Windows x64 PowerShell:

```powershell
Expand-Archive .\orion-<version>-windows-x64.zip -DestinationPath .
cd .\orion-<version>-windows-x64
.\install.ps1
orion
```

The server installer verifies the wheel and UI manifest. E5 semantic retrieval is
optional: add `--with-embeddings` on Linux or `-WithEmbeddings` on Windows to
install its dependencies and provision the pinned model. Initial installation
needs network access for uncached dependencies. See
[installation](docs/operations/INSTALLATION.md).

The portable **remote worker** is a separate artifact with its Python runtime
bundled. Customer-machine use requires no Python/Node/npm installation, service,
autostart or inbound port. Browser provisioning, platform policies and capability
limits are described in [endpoint operations](docs/operations/ENDPOINTS.md).

## Develop from source

Run `./install.sh` on Linux or `.\install.ps1` in Windows PowerShell, then
`orion`. Source installers require Python 3.12+, Node.js 22.12+ and npm.
Optional model assets stay outside the repository and verified cached assets are
reused. Default installation neither installs E5 dependencies nor downloads its
model. The same opt-in flags apply to source installers; they do not activate hybrid retrieval.

The default local UI/API is `http://127.0.0.1:61888/`. Optional remote browser
access uses owner authentication through an HTTPS tunnel/reverse proxy or private
network; a browser alone cannot grant Orion access to that browser's host OS.

See [Quickstart](docs/QUICKSTART.md), [Testing](docs/development/TESTING.md) and
[Remote Access](docs/operations/REMOTE_ACCESS.md).

## Documentation authority

Current user instructions take precedence. ADR 0016 and the consolidated baseline
define the current product boundary; compatible earlier ADRs retain their detailed
contracts. Operations documents describe implemented commands and configuration;
source/tests establish implementation evidence. Run the relevant checks before
claiming behavior works. Reading a design does not authorize a migration, deletion,
commit or push.
