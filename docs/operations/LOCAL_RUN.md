# Running Orion locally

## Web UI

```bash
orion web
```

Current CLI behavior starts the local API at `http://127.0.0.1:61888`.
It does not open a browser or manage Docker in M1.

Run the preserved UI in a second terminal:

```bash
cd ui
npm run dev
```

## Logs

```bash
orion log
```

This reports the path to the local SQLite database.

## CLI commands

Use `orion --help` to inspect the M1 CLI surface.

## Target runtime

Running locally does not change Chat/Project semantics:

```text
UI/CLI
→ backend
→ local/remote configured model
→ automatic registered tool calls
→ local integrations/RAG
→ final response
```
