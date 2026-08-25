# Quickstart

Install and start Orion:

```bash
./install.sh
orion
```

Orion opens in your default browser when it is ready.

The complete public command surface is:

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
→ model with all registered tools
→ direct answer OR automatic model-selected tool call
→ Orion executes the registered tool
→ ToolResult back to the same model
→ repeat as useful
→ final answer
```

There is no manual tool selection step in Chat or Project.
