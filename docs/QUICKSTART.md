# Quickstart

Install and start Orion on Linux:

```bash
./install.sh
orion
```

On Windows PowerShell:

```powershell
.\install.ps1
orion
```

Python 3.12+, Node.js 22.12+, and npm are required during installation. A normal install
downloads and verifies the pinned ~487 MB E5 embeddings asset when it is absent, so the first
install needs network access. The model is stored as application data outside the repository;
reruns reuse the verified cache. Installation does not run semantic indexing or enable hybrid
retrieval. `orion model install embeddings` remains available to repair or reprovision the model.

Orion opens in your default browser when it is ready.

Common commands are:

```text
orion          Start Orion
orion web      Start Orion
orion log      Show Orion logs
orion help     Show this help
```


## Development checks

For repository contributors:

```bash
make test
make lint
```

Frontend tests, when applicable:

```bash
cd ui
npm test
```

## Target Chat/Project behavior

The target runtime remains:

```text
message
→ model with all registered model-callable schemas from the first turn
→ optional exact-name expansion
→ direct answer OR automatic model-selected tool call
→ Orion executes the registered tool
→ ToolResult back to the same model
→ repeat as useful
→ final answer
```

There is no manual tool selection step in Chat or Project.
