# Quickstart

This page documents the repository's **current** installation/run path. Target architecture behavior is documented separately under `docs/architecture/`.

## Requirements

Current `install.sh` requires Python 3.12+, Node.js 22.12+, and npm. Git is useful for
normal repository/development work.

## Install

From the repository root:

```bash
./install.sh
```

The installer creates or reuses `.venv`, installs Orion, runs a deterministic frontend build,
and installs the resulting client assets for FastAPI to serve. It manages the default
`~/.local/bin/orion` launcher without touching Orion data or credentials.

## Start/use the Web UI

After installation:

```bash
orion
```

The command serves the UI and API at `http://127.0.0.1:61888/` and opens a browser once the
loopback server is ready.

Disable browser launch:

```bash
orion web --no-open
```

## Logs

```bash
orion log
```


## Development checks

Use repository targets that exist in the current checkout. Common commands are:

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
