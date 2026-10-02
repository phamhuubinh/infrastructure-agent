# Quickstart

Download the matching archive from GitHub Releases, then install and start Orion on Linux:

```bash
tar -xzf orion-<version>-linux-x86_64.tar.gz
cd orion-<version>-linux-x86_64
./install.sh
orion
```

On Windows PowerShell:

```powershell
Expand-Archive .\orion-<version>-windows-x64.zip -DestinationPath .
cd .\orion-<version>-windows-x64
.\install.ps1
orion
```

Python 3.12+ is required during release installation. A normal install
downloads and verifies the pinned ~487 MB E5 embeddings asset when it is absent, so the first
install needs network access. The model is stored as application data outside the repository;
reruns reuse the verified cache. Installation does not run semantic indexing or enable hybrid
retrieval. `orion model install embeddings` remains available to repair or reprovision the model.

Orion opens in your default browser when it is ready.

Developers using a source checkout can run the root `install.sh` or `install.ps1` instead;
those scripts require Node.js 22.12+ and npm to build the UI.

Common commands are:

```text
orion          Start Orion
orion web      Start Orion
orion log      Show Orion logs
orion help     Show this help
orion --version  Show installed Orion version
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

## Pair a remote device

Enable `ORION_ENDPOINTS=1`, create a token in Thiết bị, install the matching worker,
run configure, pair (interactive token prompt), then run. Ask Chat: “List endpoints
and inspect the system on Lab Linux.” Enable only the local roots/capabilities
needed; see [endpoint quickstart](operations/ENDPOINTS.md).
